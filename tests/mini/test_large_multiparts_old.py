# Add project root directory to Python path
import sys
from pathlib import Path
project_root = str(Path(__file__).parent.parent.parent)
sys.path.insert(0, project_root)

import unittest
import os
import tempfile
import json
import logging
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from colorama import Fore, Style, init
from driver.minio_client import MinioClient
from driver.types import OSSConfig, ProgressCallback
from tests.utils import (
    SizeFormatter, 
    ConcurrentProgressTracker,
    CallbackIOWrapper
)
from io import BytesIO

# Initialize colorama
init(autoreset=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class PartUploadProgress:
    """分片上传进度跟踪器"""
    def __init__(self, part_number: int, total_size: int):
        self.part_number = part_number
        self.total_size = total_size
        self.uploaded = 0
        self.start_time = time.time()
        self.last_update = time.time()
        self.status = 'pending'  # pending, uploading, completed, failed
        self.speed = 0
        self._lock = threading.Lock()

    def update(self, bytes_uploaded: int):
        with self._lock:
            self.uploaded += bytes_uploaded
            now = time.time()
            elapsed = now - self.last_update
            if elapsed > 0:
                self.speed = bytes_uploaded / elapsed
            self.last_update = now
            
            if self.uploaded >= self.total_size:
                self.status = 'completed'
            else:
                self.status = 'uploading'

    @property
    def progress(self) -> float:
        return (self.uploaded / self.total_size) * 100 if self.total_size > 0 else 0

    @property
    def is_stalled(self) -> bool:
        return time.time() - self.last_update > 5  # 5秒无更新视为stalled

class TestMinioLargeMultiparts(unittest.TestCase):
    """测试MinIO大文件分片上传"""
    
    def setUp(self):
        """测试初始化"""
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
            self.config = OSSConfig(**config['minio'])
        
        self.client = MinioClient(self.config)
        self.temp_dir = tempfile.mkdtemp()
        
        # 修改配置参数
        self.chunk_size = 5 * 1024 * 1024  # 5MB
        self.max_workers = 4
        self.file_size = 30  # 30MB
        
        # 存储上传状态
        self.upload = None
        self.stats = None
        self.progress_tracker = None
        self.upload_completed = False
        
        # 添加详细的调试信息
        self.part_status = {}  # 记录每个分片的状态
        self.debug_log = []   # 记录详细的调试信息
        
    def _create_large_file(self, size_mb: int) -> str:
        """创建测试用大文件"""
        file_path = os.path.join(self.temp_dir, f'large_file_{size_mb}mb.dat')
        
        # 分块写入,避免内存占用过大
        chunk_size = 5* 1024 * 1024  # 5MB chunks for creation
        remaining = size_mb * 1024 * 1024
        
        logger.info(f"Creating test file: {file_path}")
        logger.info(f"  • Target Size: {SizeFormatter.format_size(remaining)}")
        logger.info(f"  • Creation Chunk Size: {SizeFormatter.format_size(chunk_size)}")
        
        start_time = time.time()
        with open(file_path, 'wb') as f:
            while remaining > 0:
                write_size = min(chunk_size, remaining)
                f.write(os.urandom(write_size))
                remaining -= write_size
                
        creation_time = time.time() - start_time
        logger.info(f"  • File Creation Time: {creation_time:.2f}s")
        return file_path
        
    def _log_performance_stats(self, stats: dict):
        """打印性能统计信息"""
        logger.info(f"\n{Fore.CYAN}Performance Statistics:{Style.RESET_ALL}")
        logger.info(f"  • Provider: {Fore.YELLOW}MinIO{Style.RESET_ALL}")
        logger.info(f"  • Endpoint: {Fore.YELLOW}{self.config.endpoint}{Style.RESET_ALL}")
        logger.info(f"  • Bucket: {Fore.YELLOW}{self.config.bucket_name}{Style.RESET_ALL}")
        logger.info(f"  • Secure: {Fore.YELLOW}{self.config.secure}{Style.RESET_ALL}")
        logger.info(f"  • Concurrent Workers: {Fore.YELLOW}{self.max_workers}{Style.RESET_ALL}")
        logger.info(f"  • Chunk Size: {Fore.YELLOW}{SizeFormatter.format_size(self.chunk_size)}{Style.RESET_ALL}")
        logger.info(f"  • File Split Time: {Fore.YELLOW}{stats['split_time']:.2f}s{Style.RESET_ALL}")
        logger.info(f"  • Upload Time: {Fore.YELLOW}{stats['upload_time']:.2f}s{Style.RESET_ALL}")
        logger.info(f"  • Merge Time: {Fore.YELLOW}{stats['merge_time']:.2f}s{Style.RESET_ALL}")
        logger.info(f"  • Total Time: {Fore.YELLOW}{stats['total_time']:.2f}s{Style.RESET_ALL}")
        
        if stats['chunk_times']:
            avg_chunk_time = sum(stats['chunk_times']) / len(stats['chunk_times'])
            min_chunk_time = min(stats['chunk_times'])
            max_chunk_time = max(stats['chunk_times'])
            logger.info("\n  Chunk Upload Statistics:")
            logger.info(f"    • Average Time: {Fore.YELLOW}{avg_chunk_time:.2f}s{Style.RESET_ALL}")
            logger.info(f"    • Min Time: {Fore.YELLOW}{min_chunk_time:.2f}s{Style.RESET_ALL}")
            logger.info(f"    • Max Time: {Fore.YELLOW}{max_chunk_time:.2f}s{Style.RESET_ALL}")
            logger.info(f"    • Upload Speed: {Fore.YELLOW}{SizeFormatter.format_size(stats['total_size']/stats['upload_time'])}/s{Style.RESET_ALL}")
        
        logger.info("\n  Chunk Details:")
        for chunk in sorted(stats['chunks'], key=lambda x: int(x['name'].split('-')[1])):
            logger.info(f"    • {chunk['name']}: "
                       f"Size={Fore.YELLOW}{SizeFormatter.format_size(chunk['size'])}{Style.RESET_ALL}, "
                       f"Time={Fore.YELLOW}{chunk['time']:.2f}s{Style.RESET_ALL}, "
                       f"Speed={Fore.YELLOW}{SizeFormatter.format_size(chunk['size']/chunk['time'])}/s{Style.RESET_ALL}")
        
        # 添加失败统计
        if hasattr(stats, 'failed_parts') and stats.failed_parts:
            logger.info(f"\n  Failed Parts:")
            for part in stats.failed_parts:
                logger.info(f"    • Part-{part}")
        
        # 添加重试统计
        if hasattr(stats, 'retries'):
            logger.info(f"\n  Retry Statistics:")
            logger.info(f"    • Total Retries: {stats.retries}")
            logger.info(f"    • Average Retries per Part: {stats.retries/len(stats['chunks']):.2f}")

    def _upload_with_retry(self, upload_func, max_retries=3):
        """带重试的上传函数"""
        last_exception = None
        for attempt in range(max_retries):
            try:
                return upload_func()
            except Exception as e:
                last_exception = e
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2
                    logger.warning(f"Retry attempt {attempt + 1} after {wait_time}s")
                    time.sleep(wait_time)
                else:
                    raise last_exception

    def _log_debug(self, message: str):
        """记录调试信息"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        debug_msg = f"[{timestamp}] {message}"
        self.debug_log.append(debug_msg)
        logger.debug(debug_msg)

    def _upload_part(self, part_number: int, data: bytes, progress: PartUploadProgress) -> str:
        """上传单个分片"""
        try:
            self._log_debug(f"Part {part_number}: Starting upload, size={len(data)}")
            start_time = time.time()
            
            # 包装数据为可追踪进度的流
            data_stream = BytesIO(data)
            wrapped_stream = CallbackIOWrapper(
                callback=lambda bytes_read: progress.update(bytes_read),
                stream=data_stream,
                total_size=len(data)
            )
            
            # 上传分片并获取ETag
            etag = self.client.upload_part(
                upload=self.upload,
                part_number=part_number,
                data=wrapped_stream
            )
            
            # 记录完成状态
            upload_time = time.time() - start_time
            speed = len(data) / upload_time if upload_time > 0 else 0
            self._log_debug(f"Part {part_number}: Completed in {upload_time:.2f}s, Speed: {speed/1024/1024:.1f}MB/s")
            
            return etag
            
        except Exception as e:
            self._log_debug(f"Part {part_number}: Failed - {str(e)}")
            raise

    def _print_progress(self):
        """打印上传进度"""
        os.system('cls' if os.name == 'nt' else 'clear')
        print(f"Upload Progress: {len([p for p in self.part_status.values() if p.status == 'completed'])}/{len(self.part_status)} parts")
        print("=" * 70)
        
        for part_num, progress in sorted(self.part_status.items()):
            status_color = Fore.GREEN if progress.status == 'completed' else \
                          Fore.RED if progress.status == 'failed' else \
                          Fore.YELLOW
            
            bar_width = 20
            filled = int(progress.progress / 100 * bar_width)
            bar = '█' * filled + '░' * (bar_width - filled)
            
            status_text = '[completed]' if progress.status == 'completed' else \
                         '[failed]' if progress.status == 'failed' else \
                         '[uploading]'
            
            print(f"Part {part_num:<2} : {status_color}{progress.progress:>6.1f}% "
                  f"[{bar}] "
                  f"({SizeFormatter.format_size(progress.uploaded)}/"
                  f"{SizeFormatter.format_size(progress.total_size)}) - "
                  f"{SizeFormatter.format_size(progress.speed)}/s {status_text}{Style.RESET_ALL}")
        
        print("=" * 70)
        print()

    def test_multipart_upload_30mb(self):
        """测试30MB文件的分片并发上传"""
        try:
            self._log_debug(f"Starting 30MB file upload test")
            self._log_debug(f"Configuration: chunk_size={self.chunk_size}, workers={self.max_workers}")
            
            self.stats = {
                'split_time': 0,
                'upload_time': 0,
                'merge_time': 0,
                'total_time': 0,
                'total_size': 0,
                'chunk_times': [],
                'chunks': []
            }
            
            total_start_time = time.time()
            
            # 1. 创建测试文件
            self._log_debug("Creating test file...")
            file_path = self._create_large_file(self.file_size)
            
            # 2. 初始化分片上传
            object_name = 'test_30mb_multipart.dat'
            self._log_debug("Initializing multipart upload...")
            self.upload = self.client.init_multipart_upload(object_name)
            
            # 3. 准备分片上传
            file_size = os.path.getsize(file_path)
            self.stats['total_size'] = file_size
            total_parts = (file_size + self.chunk_size - 1) // self.chunk_size
            
            self._log_debug(f"File size: {SizeFormatter.format_size(file_size)}")
            self._log_debug(f"Total parts: {total_parts}")
            
            # 4. 创建进度跟踪器
            self.progress_tracker = ConcurrentProgressTracker(total_parts)
            
            # 5. 并发上传分片
            upload_start_time = time.time()
            
            # 添加进度打印线程
            def progress_printer():
                while not self.upload_completed:
                    self._print_progress()
                    time.sleep(0.5)
            
            progress_thread = threading.Thread(target=progress_printer)
            progress_thread.daemon = True
            progress_thread.start()
            
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = []
                
                # 读取并提交所有分片
                with open(file_path, 'rb') as f:
                    for part_number in range(1, total_parts + 1):
                        data = f.read(self.chunk_size)
                        if not data:
                            break
                        
                        progress = PartUploadProgress(part_number, len(data))
                        self.progress_tracker.add_part(part_number, progress)
                        
                        future = executor.submit(
                            self._upload_part,
                            part_number,
                            data,
                            progress
                        )
                        futures.append((part_number, future))
                
                # 等待所有分片完成
                for part_number, future in futures:
                    try:
                        etag = future.result(timeout=30)  # 30秒超时
                        self.upload.parts.append((part_number, etag))
                        self.progress_tracker.part_completed(part_number)
                    except Exception as e:
                        self.progress_tracker.part_failed(part_number, str(e))
                        raise
            
            self.stats['upload_time'] = time.time() - upload_start_time
            
            # 6. 完成分片上传
            self._log_debug("Starting multipart upload completion...")
            merge_start_time = time.time()
            url = self.client.complete_multipart_upload(self.upload)
            self.stats['merge_time'] = time.time() - merge_start_time
            
            self.stats['total_time'] = time.time() - total_start_time
            
            # 7. 输出详细的性能分析
            self._print_detailed_analysis()
            
            # 8. 清理
            os.unlink(file_path)
            self.client.delete_file(object_name)
            
            self.upload_completed = True
            progress_thread.join(timeout=1)
            
        except Exception as e:
            self.upload_completed = True
            raise
        finally:
            # 输出所有调试日志
            print("\nDetailed Debug Log:")
            for log in self.debug_log:
                print(log)

    def _print_detailed_analysis(self):
        """输出详细的性能分析"""
        print(f"\n{Fore.CYAN}Detailed Performance Analysis:{Style.RESET_ALL}")
        
        # 基本信息
        print("\nBasic Information:")
        print(f"  • File Size: {SizeFormatter.format_size(self.stats['total_size'])}")
        print(f"  • Chunk Size: {SizeFormatter.format_size(self.chunk_size)}")
        print(f"  • Workers: {self.max_workers}")
        
        # 时间分析
        print("\nTiming Analysis:")
        print(f"  • Total Time: {self.stats['total_time']:.2f}s")
        print(f"  • Upload Time: {self.stats['upload_time']:.2f}s")
        print(f"  • Merge Time: {self.stats['merge_time']:.2f}s")
        
        # 分片分析
        print("\nPart Analysis:")
        for part_num, status in sorted(self.part_status.items()):
            if status['status'] == 'completed':
                print(f"  Part {part_num}:")
                print(f"    • Size: {SizeFormatter.format_size(status['size'])}")
                print(f"    • Time: {status['upload_time']:.2f}s")
                print(f"    • Speed: {SizeFormatter.format_size(status['speed'])}/s")
            else:
                print(f"  Part {part_num}: {status['status']}")
                if 'error' in status:
                    print(f"    • Error: {status['error']}")

def main():
    suite = unittest.TestLoader().loadTestsFromTestCase(TestMinioLargeMultiparts)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    input("\nPress Enter to exit...")

if __name__ == '__main__':
    main() 