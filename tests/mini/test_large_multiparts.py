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
from driver.types import OSSConfig, MultipartUpload, ProgressCallback
from tests.utils import SizeFormatter, ConcurrentProgressTracker
from io import BytesIO

# Initialize colorama
init(autoreset=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class PartProgress:
    """分片上传进度跟踪"""
    def __init__(self, part_number: int, total_size: int):
        self.part_number = part_number
        self.total_size = total_size
        self.uploaded = 0
        self.start_time = time.time()
        self.last_update = time.time()
        self.completed = False
        self._lock = threading.Lock()
        self._speed_window = []  # 用于计算移动平均速度
        self._last_bytes = 0

    def __call__(self, bytes_uploaded: int):
        """回调函数，更新上传进度"""
        with self._lock:
            now = time.time()
            delta_bytes = bytes_uploaded - self._last_bytes
            delta_time = now - self.last_update
            
            if delta_time > 0:
                current_speed = delta_bytes / delta_time
                self._speed_window.append((now, current_speed))
                # 只保留最近5秒的速度数据
                self._speed_window = [(t, s) for t, s in self._speed_window if now - t <= 5]
            
            self.uploaded = bytes_uploaded
            self._last_bytes = bytes_uploaded
            self.last_update = now
            
            if self.uploaded >= self.total_size:
                self.completed = True

    @property
    def progress(self) -> float:
        return (self.uploaded / self.total_size) * 100 if self.total_size > 0 else 0

    @property
    def speed(self) -> float:
        if self.completed:
            return 0
        
        now = time.time()
        # 计算最近5秒的平均速度
        recent_speeds = [(t, s) for t, s in self._speed_window if now - t <= 5]
        if not recent_speeds:
            return 0
        return sum(s for _, s in recent_speeds) / len(recent_speeds)

class TestMinioLargeMultiparts(unittest.TestCase):
    """测试MinIO大文件分片并发上传"""
    
    def setUp(self):
        """测试初始化"""
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
            self.config = OSSConfig(**config['minio'])
        
        self.client = MinioClient(self.config)
        self.temp_dir = tempfile.mkdtemp()
        
        # 配置参数
        self.chunk_size = 5 * 1024 * 1024  # 5MB
        self.max_workers = 10
        self.file_size = 100  # 100MB
        
        # 进度跟踪
        self.progress_trackers = {}
        self.upload_completed = threading.Event()
        
    def tearDown(self):
        """清理测试环境"""
        import shutil
        shutil.rmtree(self.temp_dir)
        
    def _create_test_file(self, size_mb: int) -> str:
        """创建测试用大文件"""
        file_path = os.path.join(self.temp_dir, f'test_file_{size_mb}mb.dat')
        
        # 分块写入，避免内存占用过大
        chunk_size = 5 * 1024 * 1024  # 5MB chunks
        remaining = size_mb * 1024 * 1024
        
        logger.info(f"Creating test file: {file_path}")
        logger.info(f"  • Target Size: {SizeFormatter.format_size(remaining)}")
        
        start_time = time.time()
        with open(file_path, 'wb') as f:
            while remaining > 0:
                write_size = min(chunk_size, remaining)
                f.write(os.urandom(write_size))
                remaining -= write_size
                
        creation_time = time.time() - start_time
        logger.info(f"  • File Creation Time: {creation_time:.2f}s")
        return file_path

    def _upload_part(self, upload: MultipartUpload, part_number: int, 
                    data: bytes, progress: PartProgress = None) -> str:
        """上传单个分片"""
        try:
            logger.debug(f"Starting part {part_number} upload, size: {len(data)}")
            start_time = time.time()
            
            etag = self.client.upload_part(upload, part_number, data, progress)
            
            upload_time = time.time() - start_time
            speed = len(data) / upload_time if upload_time > 0 else 0
            logger.debug(f"Part {part_number} completed in {upload_time:.2f}s, "
                        f"speed: {SizeFormatter.format_size(speed)}/s")
            
            return etag
        except Exception as e:
            logger.error(f"Failed to upload part {part_number}: {e}")
            raise

    def _print_progress(self):
        """打印上传进度"""
        while not self.upload_completed.is_set():
            os.system('cls' if os.name == 'nt' else 'clear')
            print(f"\nUpload Progress ({len(self.progress_trackers)} parts):")
            print("=" * 70)
            
            total_speed = 0
            total_progress = 0
            
            for part_num, tracker in sorted(self.progress_trackers.items()):
                progress = tracker.progress
                speed = tracker.speed
                total_speed += speed
                total_progress += progress
                
                bar_width = 30
                filled = int(progress / 100 * bar_width)
                bar = '█' * filled + '░' * (bar_width - filled)
                
                print(f"Part {part_num:2d} [{bar}] {progress:5.1f}% "
                      f"({SizeFormatter.format_size(tracker.uploaded)}/"
                      f"{SizeFormatter.format_size(tracker.total_size)}) "
                      f"- {SizeFormatter.format_size(speed)}/s")
            
            avg_progress = total_progress / len(self.progress_trackers)
            print("\n" + "=" * 70)
            print(f"Total Progress: {avg_progress:.1f}% - "
                  f"Speed: {SizeFormatter.format_size(total_speed)}/s")
            
            time.sleep(0.5)

    def test_concurrent_multipart_upload(self):
        """测试大文件并发分片上传"""
        try:
            # 1. 创建测试文件
            file_path = self._create_test_file(self.file_size)
            file_size = os.path.getsize(file_path)
            object_name = f'concurrent_multipart_{self.file_size}mb.dat'
            
            logger.info(f"\n{Fore.CYAN}Starting Concurrent Multipart Upload Test:{Style.RESET_ALL}")
            logger.info(f"  • File Size: {SizeFormatter.format_size(file_size)}")
            logger.info(f"  • Chunk Size: {SizeFormatter.format_size(self.chunk_size)}")
            logger.info(f"  • Workers: {self.max_workers}")
            
            # 2. 初始化分片上传
            start_time = time.time()
            upload = self.client.init_multipart_upload(object_name)
            logger.info(f"  • Upload ID: {upload.upload_id}")
            
            # 3. 启动进度打印线程
            progress_thread = threading.Thread(target=self._print_progress)
            progress_thread.daemon = True
            progress_thread.start()
            
            # 4. 并发上传分片
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = []
                part_number = 1
                
                with open(file_path, 'rb') as f:
                    while True:
                        data = f.read(self.chunk_size)
                        if not data:
                            break
                            
                        # 创建进度跟踪
                        progress = PartProgress(part_number, len(data))
                        self.progress_trackers[part_number] = progress
                        
                        # 提交上传任务
                        future = executor.submit(
                            self._upload_part,
                            upload,
                            part_number,
                            data,
                            progress
                        )
                        futures.append((part_number, future))
                        part_number += 1
                
                # 等待所有分片完成
                for part_number, future in futures:
                    try:
                        etag = future.result()
                        upload.parts.append((part_number, etag))
                        logger.info(f"  • Part {part_number} completed, ETag: {etag}")
                    except Exception as e:
                        logger.error(f"  • Part {part_number} failed: {e}")
                        raise
            
            # 5. 完成上传
            logger.info(f"\n{'-'*20} Starting Multipart Upload Completion {'-'*20}")
            completion_start = time.time()
            
            # 记录所有分片信息
            logger.info("\nPart Information:")
            for part_num, etag in sorted(upload.parts):
                logger.info(f"  • Part {part_num:2d}: {etag}")
            
            result_url = self.client.complete_multipart_upload(upload)
            completion_time = time.time() - completion_start
            logger.info(f"\nMultipart upload completion took {completion_time:.2f}s")
            
            # 6. 验证上传
            logger.info(f"\n{'-'*20} Starting Download Verification {'-'*20}")
            verify_start = time.time()
            downloaded_path = os.path.join(self.temp_dir, 'downloaded.dat')
            
            # 记录下载过程
            logger.info("Downloading file for verification...")
            download_start = time.time()
            self.client.download_file(object_name, downloaded_path)
            download_time = time.time() - download_start
            logger.info(f"Download took {download_time:.2f}s")
            
            # 验证文件大小
            original_size = os.path.getsize(file_path)
            downloaded_size = os.path.getsize(downloaded_path)
            logger.info(f"\nSize Verification:")
            logger.info(f"  • Original: {SizeFormatter.format_size(original_size)}")
            logger.info(f"  • Downloaded: {SizeFormatter.format_size(downloaded_size)}")
            
            self.assertEqual(
                original_size,
                downloaded_size,
                "Downloaded file size doesn't match original"
            )
            
            verify_time = time.time() - verify_start
            logger.info(f"Total verification took {verify_time:.2f}s")
            
            # 7. 清理
            cleanup_start = time.time()
            self.client.delete_file(object_name)
            cleanup_time = time.time() - cleanup_start
            logger.info(f"\nCleanup took {cleanup_time:.2f}s")
            
            # 8. 输出完整统计信息
            total_time = time.time() - start_time
            logger.info(f"\n{'-'*20} Upload Statistics {'-'*20}")
            logger.info(f"  • Upload Time: {completion_start - start_time:.2f}s")
            logger.info(f"  • Completion Time: {completion_time:.2f}s")
            logger.info(f"  • Verification Time: {verify_time:.2f}s")
            logger.info(f"  • Cleanup Time: {cleanup_time:.2f}s")
            logger.info(f"  • Total Time: {total_time:.2f}s")
            logger.info(f"  • Average Speed: {SizeFormatter.format_size(original_size/total_time)}/s")
            
        finally:
            self.upload_completed.set()

def main():
    suite = unittest.TestLoader().loadTestsFromTestCase(TestMinioLargeMultiparts)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    input("\nPress Enter to exit...")

if __name__ == '__main__':
    main() 