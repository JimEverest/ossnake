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
import signal
import functools
from datetime import datetime
from colorama import Fore, Style, init
from driver.minio_client import MinioClient
from driver.types import OSSConfig, ProgressCallback
from driver.exceptions import *

# Initialize colorama
init(autoreset=True)

# Configure logging
log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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

class TestMinioBasicOperations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Print test list before running any tests"""
        print(f"\n{Fore.CYAN}╔══════════════════════════════════════════════════════════════╗{Style.RESET_ALL}")
        print(f"{Fore.CYAN}║               MinIO Basic Operations Tests                  ║{Style.RESET_ALL}")
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
        
        # Verify connection and bucket
        try:
            logger.info("Verifying MinIO connection...")
            if not self.client.client.bucket_exists(self.config.bucket_name):
                logger.info(f"Creating bucket: {self.config.bucket_name}")
                self.client.client.make_bucket(self.config.bucket_name)
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
            logger.error(f"Failed to clean up temporary directory: {str(e)}")
            
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
    def test_upload_and_download(self):
        """Test basic file upload and download"""
        logger.info(f"{Fore.MAGENTA}---------- Test: {self._testMethodName} ----------{Style.RESET_ALL}")
        try:
            # Create test file (1MB)
            object_name = 'test_upload.dat'
            file_path = self._create_test_file(1, 'test_file_1mb.dat')
            logger.info(f"  {Fore.BLUE}1. Created test file: {file_path} (1MB){Style.RESET_ALL}")
            
            # Upload file
            start_time = time.time()
            url = self.client.upload_file(file_path, object_name)
            upload_time = time.time() - start_time
            logger.info(f"  {Fore.GREEN}2. File uploaded, URL: {url}{Style.RESET_ALL}")
            logger.info(f"  {Fore.GREEN}3. Upload time: {upload_time:.2f}s{Style.RESET_ALL}")
            
            # Download and verify
            download_path = os.path.join(self.temp_dir, 'downloaded.dat')
            self.client.download_file(object_name, download_path)
            self.assertEqual(os.path.getsize(file_path), os.path.getsize(download_path))
            logger.info(f"  {Fore.GREEN}4. File size verification passed{Style.RESET_ALL}")
            
            # Clean up
            self.client.delete_file(object_name)
            logger.info(f"  {Fore.BLUE}5. Cleaned up test file{Style.RESET_ALL}")
            
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

    @timeout(30)
    def test_delete_file(self):
        """Test file deletion"""
        logger.info(f"{Fore.MAGENTA}---------- Test: {self._testMethodName} ----------{Style.RESET_ALL}")
        try:
            # Create and upload test file
            object_name = 'test_delete.dat'
            file_path = self._create_test_file(1, 'test_file_1mb.dat')
            logger.info(f"  {Fore.BLUE}1. Created test file: {file_path} (1MB){Style.RESET_ALL}")
            
            url = self.client.upload_file(file_path, object_name)
            logger.info(f"  {Fore.BLUE}2. File uploaded, URL: {url}{Style.RESET_ALL}")
            
            # Delete file
            start_time = time.time()
            self.client.delete_file(object_name)
            delete_time = time.time() - start_time
            logger.info(f"  {Fore.GREEN}3. File deleted{Style.RESET_ALL}")
            
            # Verify file is deleted
            try:
                self.client.download_file(object_name, os.path.join(self.temp_dir, 'should_not_exist.dat'))
                self.fail("File should not exist after deletion")
            except ObjectNotFoundError:
                logger.info(f"  {Fore.GREEN}4. Verified file does not exist (expected){Style.RESET_ALL}")
            
            return {
                'name': self._testMethodName,
                'result': 'PASSED',
                'time': delete_time
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

    @timeout(60)  # 更长的超时时间，因为要上传多个文件
    def test_list_objects(self):
        """Test listing objects"""
        logger.info(f"{Fore.MAGENTA}---------- Test: {self._testMethodName} ----------{Style.RESET_ALL}")
        try:
            # Upload multiple test files
            test_files = [
                ('test_list_1.dat', 1),
                ('test_list_2.dat', 2),
                ('test_list_3.dat', 1)
            ]
            
            logger.info(f"  {Fore.BLUE}1. Creating and uploading test files...{Style.RESET_ALL}")
            for object_name, size in test_files:
                file_path = self._create_test_file(size, f'test_file_{size}mb.dat')
                url = self.client.upload_file(file_path, object_name)
                logger.info(f"    - Uploaded {object_name} ({size}MB)")
            
            # List objects
            start_time = time.time()
            objects = self.client.list_objects(prefix='test_list_')
            list_time = time.time() - start_time
            
            # Verify results
            self.assertEqual(len(objects), len(test_files))
            logger.info(f"  {Fore.GREEN}2. Listed {len(objects)} objects:{Style.RESET_ALL}")
            for obj in objects:
                logger.info(f"    - {obj['name']} ({obj['size']} bytes)")
            
            # Clean up
            logger.info(f"  {Fore.BLUE}3. Cleaning up test files...{Style.RESET_ALL}")
            for object_name, _ in test_files:
                self.client.delete_file(object_name)
            
            return {
                'name': self._testMethodName,
                'result': 'PASSED',
                'time': list_time
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

    @timeout(30)
    def test_get_presigned_url(self):
        """Test generating presigned URLs"""
        logger.info(f"{Fore.MAGENTA}---------- Test: {self._testMethodName} ----------{Style.RESET_ALL}")
        try:
            # Create and upload test file
            object_name = 'test_presigned.dat'
            file_path = self._create_test_file(1, 'test_file_1mb.dat')
            logger.info(f"  {Fore.BLUE}1. Created test file: {file_path} (1MB){Style.RESET_ALL}")
            
            url = self.client.upload_file(file_path, object_name)
            logger.info(f"  {Fore.BLUE}2. File uploaded, URL: {url}{Style.RESET_ALL}")
            
            # Generate presigned URL
            start_time = time.time()
            presigned_url = self.client.get_presigned_url(object_name, expires=3600)
            generate_time = time.time() - start_time
            
            # Verify URL format and accessibility
            self.assertTrue(presigned_url.startswith('http'))
            self.assertIn(object_name, presigned_url)
            logger.info(f"  {Fore.GREEN}3. Generated presigned URL: {presigned_url}{Style.RESET_ALL}")
            
            # Clean up
            self.client.delete_file(object_name)
            logger.info(f"  {Fore.BLUE}4. Cleaned up test file{Style.RESET_ALL}")
            
            return {
                'name': self._testMethodName,
                'result': 'PASSED',
                'time': generate_time
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
    suite = unittest.TestLoader().loadTestsFromTestCase(TestMinioBasicOperations)
    runner = CustomTestRunner(verbosity=2)
    result = runner.run(suite)
    result.printReport()
    
    # 等待用户按键后退出
    input("\nPress Enter to exit...")

if __name__ == '__main__':
    main() 