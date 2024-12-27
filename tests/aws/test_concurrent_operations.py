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
import traceback
import time
import threading
import queue
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from colorama import Fore, Style, init
from driver.aws_s3 import AWSS3Client
from driver.types import OSSConfig, ProgressCallback
from driver.exceptions import *

# Initialize colorama
init(autoreset=True)

# Configure logging
log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ConcurrentProgressTracker:
    """跟踪多个文件的并发上传进度"""
    def __init__(self, total_files: int):
        self.lock = threading.Lock()
        self.progress_by_file = {}  # 每个文件的进度
        self.total_files = total_files
        self.completed_files = 0
        self.start_time = time.time()
        
    def update_progress(self, file_name: str, bytes_transferred: int, total_bytes: int):
        """更新指定文件的进度"""
        with self.lock:
            elapsed = time.time() - self.start_time
            speed = bytes_transferred / elapsed if elapsed > 0 else 0
            
            self.progress_by_file[file_name] = {
                'transferred': bytes_transferred,
                'total': total_bytes,
                'percentage': (bytes_transferred / total_bytes) * 100,
                'speed': speed,
                'completed': False
            }
            self._print_progress()
    
    def file_completed(self, file_name: str):
        """标记文件完成"""
        with self.lock:
            self.completed_files += 1
            if file_name in self.progress_by_file:
                self.progress_by_file[file_name]['completed'] = True
            self._print_progress()
    
    def _print_progress(self):
        """打印所有文件的进度"""
        # 清除当前行
        print('\033[K', end='\r')
        
        # 显示总体进度
        print(f"\n{Fore.CYAN}Concurrent Upload Progress ({self.completed_files}/{self.total_files} files):{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*70}{Style.RESET_ALL}")
        
        # 显示每个文件的进度
        for file_name, progress in sorted(self.progress_by_file.items()):
            status_color = Fore.GREEN if progress['completed'] else Fore.YELLOW
            speed_mb = progress['speed'] / 1024 / 1024  # Convert to MB/s
            
            print(f"{status_color}{file_name:<15}: "
                  f"{progress['percentage']:>6.1f}% "
                  f"({self._format_size(progress['transferred'])}/{self._format_size(progress['total'])}) "
                  f"- {speed_mb:.1f} MB/s{Style.RESET_ALL}")
        
        print(f"{Fore.CYAN}{'='*70}{Style.RESET_ALL}")
        # 移动光标到进度显示开始处
        print('\033[F' * (len(self.progress_by_file) + 3), end='')

    def _format_size(self, size_bytes: int) -> str:
        """格式化文件大小显示"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024:
                return f"{size_bytes:.1f}{unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f}TB"

class TestAWSConcurrentOperations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """设置测试类"""
        print(f"\n{Fore.CYAN}╔══════════════════════════════════════════════════════════════╗{Style.RESET_ALL}")
        print(f"{Fore.CYAN}║             AWS S3 Concurrent Operations Tests              ║{Style.RESET_ALL}")
        print(f"{Fore.CYAN}╚══════════════════════════════════════════════════════════════╝{Style.RESET_ALL}")
        
        test_methods = [m for m in dir(cls) if m.startswith('test_')]
        print("\nTests to be executed:")
        for i, method in enumerate(test_methods, 1):
            print(f"  {i}. {method}")
        print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")

    def setUp(self):
        """每个测试前的设置"""
        logger.info(f"Setting up test: {self._testMethodName}")
        # 加载配置
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
            self.config = OSSConfig(**config['aws'])
        
        # 创建临时目录
        self.temp_dir = tempfile.mkdtemp()
        logger.info(f"  - Temporary directory created: {self.temp_dir}")
        
        # 初始化客户端
        self.client = AWSS3Client(self.config)

    def tearDown(self):
        """每个测试后的清理"""
        logger.info(f"Tearing down test: {self._testMethodName}")
        # 清理临时目录
        if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
            import shutil
            shutil.rmtree(self.temp_dir)
            logger.info(f"  - Temporary directory removed: {self.temp_dir}")

    def _create_test_file(self, size_mb: int, filename: str = None) -> str:
        """创建指定大小的测试文件"""
        if filename is None:
            filename = f'test_file_{size_mb}mb.dat'
        file_path = os.path.join(self.temp_dir, filename)
        
        # 创建指定大小的文件
        with open(file_path, 'wb') as f:
            f.write(os.urandom(size_mb * 1024 * 1024))
        
        return file_path

    def test_concurrent_uploads(self):
        """测试并发文件上传与进度跟踪"""
        logger.info(f"{Fore.MAGENTA}---------- Test: {self._testMethodName} ----------{Style.RESET_ALL}")
        try:
            # 创建测试文件
            test_files = [
                ('concurrent_1.dat', 5),  # 5MB
                ('concurrent_2.dat', 3),  # 3MB
                ('concurrent_3.dat', 4),  # 4MB
                ('concurrent_4.dat', 2)   # 2MB
            ]
            
            logger.info(f"  {Fore.BLUE}1. Creating test files...{Style.RESET_ALL}")
            file_paths = []
            for object_name, size in test_files:
                file_path = self._create_test_file(size, object_name)
                file_paths.append((object_name, file_path))
                logger.info(f"    - Created {object_name} ({size}MB)")
            
            # 初始化进度跟踪器
            progress_tracker = ConcurrentProgressTracker(len(test_files))
            
            def upload_file(object_name: str, file_path: str):
                """单个文件上传函数"""
                try:
                    def progress_callback(bytes_transferred: int, total_bytes: int):
                        progress_tracker.update_progress(object_name, bytes_transferred, total_bytes)
                    
                    url = self.client.upload_file(
                        file_path,
                        object_name,
                        progress_callback=progress_callback
                    )
                    progress_tracker.file_completed(object_name)
                    return url
                except Exception as e:
                    logger.error(f"Failed to upload {object_name}: {str(e)}")
                    raise
            
            # 并发上传
            start_time = time.time()
            urls = []
            
            with ThreadPoolExecutor(max_workers=4) as executor:
                # 提交所有上传任务
                future_to_file = {
                    executor.submit(upload_file, obj_name, path): obj_name
                    for obj_name, path in file_paths
                }
                
                # 使用as_completed获取完成的任务
                for future in as_completed(future_to_file):
                    file_name = future_to_file[future]
                    try:
                        url = future.result(timeout=60)  # 60秒超时
                        urls.append(url)
                        logger.info(f"  {Fore.GREEN}- Uploaded {file_name}: {url}{Style.RESET_ALL}")
                    except Exception as e:
                        logger.error(f"  {Fore.RED}- Failed to upload {file_name}: {str(e)}{Style.RESET_ALL}")
                        raise
            
            # 清除进度显示
            print('\n' * (len(test_files) + 3))
            
            upload_time = time.time() - start_time
            logger.info(f"  {Fore.GREEN}2. All files uploaded in {upload_time:.2f}s{Style.RESET_ALL}")
            
            # 验证所有文件都已上传
            self.assertEqual(len(urls), len(test_files))
            
            # 清理
            logger.info(f"  {Fore.BLUE}3. Cleaning up test files...{Style.RESET_ALL}")
            for object_name, _ in test_files:
                self.client.delete_file(object_name)
            
            return {
                'name': self._testMethodName,
                'result': 'PASSED',
                'time': upload_time
            }
        except Exception as e:
            logger.error(f"Test {self._testMethodName} {Fore.RED}FAILED{Style.RESET_ALL}")
            logger.error(f"  {Fore.RED}- Exception: {str(e)}{Style.RESET_ALL}")
            logger.error(f"  {Fore.RED}- Traceback: {traceback.format_exc()}{Style.RESET_ALL}")
            return {
                'name': self._testMethodName,
                'result': 'FAILED',
                'time': 0
            }

    def test_progress_callback(self):
        """测试单文件上传进度回调"""
        logger.info(f"{Fore.MAGENTA}---------- Test: {self._testMethodName} ----------{Style.RESET_ALL}")
        try:
            # Create a test file (10MB)
            object_name = 'progress_test.dat'
            file_path = self._create_test_file(10, 'test_file_10mb.dat')
            logger.info(f"  {Fore.BLUE}1. Created test file: {file_path} (10MB){Style.RESET_ALL}")
            
            # Track progress
            progress_updates = []
            def progress_callback(bytes_transferred: int, total_bytes: int):
                progress = (bytes_transferred / total_bytes) * 100 if total_bytes > 0 else 0
                progress_updates.append(progress)
                logger.info(f"  Progress: {progress:.1f}% ({bytes_transferred}/{total_bytes} bytes)")
            
            # Upload with progress tracking
            start_time = time.time()
            url = self.client.upload_file(
                file_path, 
                object_name,
                progress_callback=progress_callback
            )
            upload_time = time.time() - start_time
            
            # Verify progress tracking
            self.assertTrue(len(progress_updates) > 0, "No progress updates received")
            self.assertGreater(progress_updates[-1], 0, "Final progress should be greater than 0%")
            logger.info(f"  {Fore.GREEN}2. File uploaded with {len(progress_updates)} progress updates{Style.RESET_ALL}")
            logger.info(f"  {Fore.GREEN}3. Upload completed in {upload_time:.2f}s{Style.RESET_ALL}")
            
            # Clean up
            self.client.delete_file(object_name)
            logger.info(f"  {Fore.BLUE}4. Cleaned up test file{Style.RESET_ALL}")
            
            return {
                'name': self._testMethodName,
                'result': 'PASSED',
                'time': upload_time
            }
        except Exception as e:
            logger.error(f"Test {self._testMethodName} {Fore.RED}FAILED{Style.RESET_ALL}")
            logger.error(f"  {Fore.RED}- Exception: {str(e)}{Style.RESET_ALL}")
            logger.error(f"  {Fore.RED}- Traceback: {traceback.format_exc()}{Style.RESET_ALL}")
            return {
                'name': self._testMethodName,
                'result': 'FAILED',
                'time': 0
            }

class CustomTestResult(unittest.TextTestResult):
    def __init__(self, stream, descriptions, verbosity):
        super().__init__(stream, descriptions, verbosity)
        self.test_results = []

    def startTest(self, test):
        self.start_time = time.time()
        super().startTest(test)

    def stopTest(self, test):
        elapsed_time = time.time() - self.start_time
        # 检查测试是否成功
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
        print(f"{Fore.CYAN}║                        Test Report                           ║{Style.RESET_ALL}")
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

def main():
    suite = unittest.TestLoader().loadTestsFromTestCase(TestAWSConcurrentOperations)
    runner = CustomTestRunner(verbosity=2)
    result = runner.run(suite)
    result.printReport()
    
    # 等待用户按键后退出
    input("\nPress Enter to exit...")

if __name__ == '__main__':
    main() 