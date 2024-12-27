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
from driver.aws_s3 import AWSS3Client
from driver.types import OSSConfig, ProgressCallback
from tests.utils import SizeFormatter, ConcurrentProgressTracker

# Initialize colorama
init(autoreset=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TestAWSLargeMultiparts(unittest.TestCase):
    """测试AWS S3大文件分片上传"""
    
    def setUp(self):
        """测试初始化"""
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
            self.config = OSSConfig(**config['aws'])
        
        self.client = AWSS3Client(self.config)
        self.temp_dir = tempfile.mkdtemp()
        
        # 可配置参数
        self.chunk_size = 5 * 1024 * 1024  # 5MB 
        self.max_workers = 8  # 并发数
        
    def _create_large_file(self, size_mb: int) -> str:
        """创建测试用大文件"""
        file_path = os.path.join(self.temp_dir, f'large_file_{size_mb}mb.dat')
        
        # 分块写入,避免内存占用过大
        chunk_size = 1024 * 1024  # 1MB
        remaining = size_mb * 1024 * 1024
        
        with open(file_path, 'wb') as f:
            while remaining > 0:
                write_size = min(chunk_size, remaining)
                f.write(os.urandom(write_size))
                remaining -= write_size
                
        return file_path
        
    def _log_performance_stats(self, stats: dict):
        """打印性能统计信息"""
        logger.info(f"\n{Fore.CYAN}Performance Statistics:{Style.RESET_ALL}")
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
        
        logger.info("\n  Chunk Details:")
        for chunk in stats['chunks']:
            logger.info(f"    • {chunk['name']}: "
                       f"Size={Fore.YELLOW}{SizeFormatter.format_size(chunk['size'])}{Style.RESET_ALL}, "
                       f"Time={Fore.YELLOW}{chunk['time']:.2f}s{Style.RESET_ALL}")

    def test_large_file_multipart_upload(self):
        """测试100MB文件的分片并发上传"""
        try:
            stats = {
                'split_time': 0,
                'upload_time': 0,
                'merge_time': 0,
                'total_time': 0,
                'chunk_times': [],
                'chunks': []
            }
            
            total_start_time = time.time()
            
            # 1. 创建测试文件
            file_size = 100  # 100MB
            file_path = self._create_large_file(file_size)
            logger.info(f"Created test file: {file_path} ({file_size}MB)")
            
            # 2. 初始化分片上传
            object_name = 'large_multipart.dat'
            upload = self.client.init_multipart_upload(object_name)
            logger.info(f"Initialized multipart upload: {upload.upload_id}")
            
            # 3. 准备分片上传
            split_start_time = time.time()
            file_size = os.path.getsize(file_path)
            total_parts = (file_size + self.chunk_size - 1) // self.chunk_size
            stats['split_time'] = time.time() - split_start_time
            
            logger.info(f"\n{Fore.CYAN}Splitting file:{Style.RESET_ALL}")
            logger.info(f"  • Total Size: {SizeFormatter.format_size(file_size)}")
            logger.info(f"  • Chunk Size: {SizeFormatter.format_size(self.chunk_size)}")
            logger.info(f"  • Total Parts: {total_parts}")
            logger.info(f"  • Split Time: {stats['split_time']:.2f}s")
            
            # 4. 创建进度跟踪器
            progress_tracker = ConcurrentProgressTracker(total_parts)
            
            # 5. 定义分片上传函数
            def upload_part(part_number: int, data: bytes) -> tuple:
                try:
                    chunk_start_time = time.time()
                    etag = self.client.upload_part(upload, part_number, data)
                    chunk_time = time.time() - chunk_start_time
                    
                    chunk_info = {
                        'name': f'Part-{part_number}',
                        'size': len(data),
                        'time': chunk_time
                    }
                    stats['chunks'].append(chunk_info)
                    stats['chunk_times'].append(chunk_time)
                    
                    progress_tracker.update_progress(
                        f"Part {part_number}",
                        len(data),
                        self.chunk_size
                    )
                    return part_number, etag
                except Exception as e:
                    logger.error(f"Failed to upload part {part_number}: {e}")
                    raise
            
            # 6. 并发上传分片
            upload_start_time = time.time()
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = []
                with open(file_path, 'rb') as f:
                    part_number = 1
                    while True:
                        data = f.read(self.chunk_size)
                        if not data:
                            break
                            
                        future = executor.submit(upload_part, part_number, data)
                        futures.append(future)
                        part_number += 1
                
                # 等待所有分片上传完成
                for future in as_completed(futures):
                    part_number, etag = future.result()
                    upload.parts.append((part_number, etag))
                    progress_tracker.file_completed(f"Part {part_number}")
                
            stats['upload_time'] = time.time() - upload_start_time
            
            # 7. 完成分片上传
            merge_start_time = time.time()
            url = self.client.complete_multipart_upload(upload)
            stats['merge_time'] = time.time() - merge_start_time
            
            stats['total_time'] = time.time() - total_start_time
            
            # 8. 输出性能统计
            self._log_performance_stats(stats)
            
            # 9. 验证上传结果
            logger.info(f"\n{Fore.GREEN}Upload successful:{Style.RESET_ALL}")
            logger.info(f"  • File URL: {url}")
            
            # 10. 清理测试文件
            os.unlink(file_path)
            self.client.delete_file(object_name)
            
        except Exception as e:
            logger.error(f"Test failed: {e}")
            raise

    def tearDown(self):
        """清理测试环境"""
        logger.info(f"Tearing down test: {self._testMethodName}")
        if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
            import shutil
            shutil.rmtree(self.temp_dir)
            logger.info(f"  - Temporary directory removed: {self.temp_dir}")

class CustomTestResult(unittest.TextTestResult):
    def __init__(self, stream, descriptions, verbosity):
        super().__init__(stream, descriptions, verbosity)
        self.test_results = []
        self.start_time = None

    def startTest(self, test):
        self.start_time = time.time()
        super().startTest(test)

    def stopTest(self, test):
        elapsed_time = time.time() - self.start_time
        test_result = 'PASSED'
        if len(self.failures) > 0 and test in [f[0] for f in self.failures]:
            test_result = 'FAILED'
        elif len(self.errors) > 0 and test in [e[0] for e in self.errors]:
            test_result = 'FAILED'
        elif len(self.skipped) > 0 and test in [s[0] for s in self.skipped]:
            test_result = 'SKIPPED'
        
        self.test_results.append({
            'name': test._testMethodName,
            'result': test_result,
            'time': elapsed_time
        })
        super().stopTest(test)

    def printReport(self):
        print(f"\n{Fore.CYAN}╔══════════════════════════════════════════════════════════════╗{Style.RESET_ALL}")
        print(f"{Fore.CYAN}║                   Large File Upload Test Report               ║{Style.RESET_ALL}")
        print(f"{Fore.CYAN}╚══════════════════════════════════════════════════════════════╝{Style.RESET_ALL}\n")
        
        total_time = 0
        passed = 0
        failed = 0
        
        for test_result in self.test_results:
            status_color = Fore.GREEN if test_result['result'] == 'PASSED' else Fore.RED
            print(f"  • Test: {test_result['name']}")
            print(f"    Status: {status_color}{test_result['result']}{Style.RESET_ALL}")
            print(f"    Time: {Fore.YELLOW}{test_result['time']:.2f}s{Style.RESET_ALL}")
            print()
            
            total_time += test_result['time']
            if test_result['result'] == 'PASSED':
                passed += 1
            else:
                failed += 1
        
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
        print(f"\nSummary:")
        print(f"  • Total Tests: {passed + failed}")
        print(f"  • Passed: {Fore.GREEN}{passed}{Style.RESET_ALL}")
        print(f"  • Failed: {Fore.RED}{failed}{Style.RESET_ALL}")
        print(f"  • Total Time: {Fore.YELLOW}{total_time:.2f}s{Style.RESET_ALL}")
        print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")

class CustomTestRunner(unittest.TextTestRunner):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.resultclass = CustomTestResult
    
    def run(self, test):
        "Run the given test case or test suite."
        # Print test header
        print(f"\n{Fore.CYAN}╔══════════════════════════════════════════════════════════════╗{Style.RESET_ALL}")
        print(f"{Fore.CYAN}║                AWS S3 Large File Upload Tests                 ║{Style.RESET_ALL}")
        print(f"{Fore.CYAN}╚═════════════════════════════════���════════════════════════════╝{Style.RESET_ALL}")
        
        # Print test list
        test_methods = [m for m in dir(TestAWSLargeMultiparts) if m.startswith('test_')]
        print(f"\n{Fore.YELLOW}Tests to be executed:{Style.RESET_ALL}")
        for i, method in enumerate(test_methods, 1):
            print(f"  {i}. {method}")
        print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")

        result = super().run(test)
        result.printReport()
        return result

def main():
    suite = unittest.TestLoader().loadTestsFromTestCase(TestAWSLargeMultiparts)
    runner = CustomTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # 等待用户按键后退出
    input("\nPress Enter to exit...")

if __name__ == '__main__':
    main()
