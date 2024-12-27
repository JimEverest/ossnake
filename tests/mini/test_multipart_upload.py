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
from datetime import datetime
from colorama import Fore, Style, init
from driver.minio_client import MinioClient
from driver.types import OSSConfig, ProgressCallback
from driver.exceptions import *
import functools
import signal

# Initialize colorama
init(autoreset=True)

# Configure logging
log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def format_file_size(size_in_bytes):
    """Format file size in bytes to human readable format"""
    if size_in_bytes < 1024:
        return f"{size_in_bytes} bytes"
    elif size_in_bytes < 1024 * 1024:
        return f"{size_in_bytes/1024:.2f} KB"
    else:
        return f"{size_in_bytes/(1024*1024):.2f} MB"

def timeout(seconds):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            def handler(signum, frame):
                raise TimeoutError(f"Test timed out after {seconds} seconds")
            
            # Set the timeout handler
            signal.signal(signal.SIGALRM, handler)
            signal.alarm(seconds)
            
            try:
                result = func(*args, **kwargs)
            finally:
                # Disable the alarm
                signal.alarm(0)
            return result
        return wrapper
    return decorator

class TestMinioMultipartUpload(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Print test list before running any tests"""
        print(f"\n{Fore.CYAN}╔══════════════════════════════════════════════════════════════╗{Style.RESET_ALL}")
        print(f"{Fore.CYAN}║               MinIO Multipart Upload Tests                  ║{Style.RESET_ALL}")
        print(f"{Fore.CYAN}╚══════════════════════════════════════════════════════════════╝{Style.RESET_ALL}")
        
        test_methods = [m for m in dir(cls) if m.startswith('test_')]
        print(f"\n{Fore.YELLOW}Tests to be executed:{Style.RESET_ALL}")
        for i, method in enumerate(test_methods, 1):
            print(f"  {i}. {method}")
        print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")

    def setUp(self):
        """Set up test environment before each test"""
        logger.info(f"Setting up test: {self._testMethodName}")
        # Load config from config.json
        with open('config.json', 'r') as f:
            config_data = json.load(f)
            minio_config = config_data.get('minio', {})
            self.config = OSSConfig(**minio_config)
            
        logger.info(f"Connecting to MinIO server at {self.config.endpoint}")
        # Create an instance of the client
        self.client = MinioClient(self.config)
        
        # Verify connection
        try:
            logger.info("Verifying MinIO connection...")
            self.client.client.bucket_exists(self.config.bucket_name)
            logger.info("Successfully connected to MinIO server")
        except Exception as e:
            logger.error(f"Failed to connect to MinIO server: {str(e)}")
            raise

        # Create a temporary directory for testing
        self.temp_dir = tempfile.mkdtemp()
        logger.info(f"  {Fore.CYAN}- Temporary directory created: {self.temp_dir}{Style.RESET_ALL}")

    def tearDown(self):
        """Clean up test environment after each test"""
        logger.info(f"Tearing down test: {self._testMethodName}")
        try:
            # Clean up the temporary directory
            import shutil
            shutil.rmtree(self.temp_dir)
            logger.info(f"  {Fore.CYAN}- Temporary directory removed: {self.temp_dir}{Style.RESET_ALL}")
        except Exception as e:
            logger.error(f"Failed to clean up: {str(e)}")
            
        # Force close any hanging connections
        try:
            self.client.client._http.clear()
        except:
            pass

    def _create_test_file(self, size_mb: int, filename: str) -> str:
        """Create a test file with random content"""
        file_path = os.path.join(self.temp_dir, filename)
        with open(file_path, 'wb') as f:
            f.write(os.urandom(size_mb * 1024 * 1024))
        return file_path 

    @timeout(30)  # 30秒超时
    def test_multipart_upload_small_file(self):
        """Test multipart upload with a small file (5MB)"""
        logger.info(f"{Fore.MAGENTA}---------- Test: {self._testMethodName} ----------{Style.RESET_ALL}")
        try:
            # 测试开始前先检查连接
            try:
                self.client.client.bucket_exists(self.config.bucket_name)
            except Exception as e:
                raise ConnectionError(f"Failed to connect to MinIO server: {str(e)}")

            # Create test file (5MB)
            object_name = 'multipart_small.dat'
            file_path = self._create_test_file(5, 'test_file_5mb.dat')
            logger.info(f"  {Fore.BLUE}1. Created test file: {file_path} (5MB){Style.RESET_ALL}")
            
            # Initialize multipart upload
            upload = self.client.init_multipart_upload(object_name)
            logger.info(f"  {Fore.BLUE}2. Initialized multipart upload with ID: {upload.upload_id}{Style.RESET_ALL}")
            
            # Upload part
            start_time = time.time()
            with open(file_path, 'rb') as f:
                data = f.read()
                etag = self.client.upload_part(upload, 1, data)
                upload.parts.append((1, etag))
            logger.info(f"  {Fore.GREEN}3. Uploaded part 1, ETag: {etag}{Style.RESET_ALL}")
            
            # Complete upload
            url = self.client.complete_multipart_upload(upload)
            upload_time = time.time() - start_time
            logger.info(f"  {Fore.GREEN}4. Multipart upload completed, URL: {url}{Style.RESET_ALL}")
            logger.info(f"  {Fore.GREEN}5. Upload time: {upload_time:.2f}s{Style.RESET_ALL}")
            
            # Verify file size
            download_path = os.path.join(self.temp_dir, 'downloaded.dat')
            self.client.download_file(object_name, download_path)
            self.assertEqual(os.path.getsize(file_path), os.path.getsize(download_path))
            logger.info(f"  {Fore.GREEN}6. File size verification passed{Style.RESET_ALL}")
            
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
    suite = unittest.TestLoader().loadTestsFromTestCase(TestMinioMultipartUpload)
    runner = CustomTestRunner(verbosity=2)
    result = runner.run(suite)
    result.printReport()

if __name__ == '__main__':
    main() 