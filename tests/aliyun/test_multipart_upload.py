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
from driver.oss_ali import AliyunOSSClient
from driver.types import OSSConfig, ProgressCallback
from driver.exceptions import *

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

class TestAliyunMultipartUpload(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Print test list before running any tests"""
        print(f"\n{Fore.CYAN}╔══════════════════════════════════════════════════════════════╗{Style.RESET_ALL}")
        print(f"{Fore.CYAN}║              Aliyun OSS Multipart Upload Tests              ║{Style.RESET_ALL}")
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
            aliyun_config = config_data.get('aliyun', {})
            self.config = OSSConfig(**aliyun_config)

        # Create an instance of the client
        self.client = AliyunOSSClient(self.config)

        # Create a temporary directory for testing
        self.temp_dir = tempfile.mkdtemp()
        logger.info(f"  {Fore.CYAN}- Temporary directory created: {self.temp_dir}{Style.RESET_ALL}")

    def tearDown(self):
        """Clean up test environment after each test"""
        logger.info(f"Tearing down test: {self._testMethodName}")
        # Clean up the temporary directory
        import shutil
        shutil.rmtree(self.temp_dir)
        logger.info(f"  {Fore.CYAN}- Temporary directory removed: {self.temp_dir}{Style.RESET_ALL}")

    def _create_test_file(self, size_mb: int, filename: str) -> str:
        """Create a test file with random content"""
        file_path = os.path.join(self.temp_dir, filename)
        with open(file_path, 'wb') as f:
            f.write(os.urandom(size_mb * 1024 * 1024))
        return file_path

    def test_multipart_upload_small_file(self):
        """Test multipart upload with a small file (5MB)"""
        logger.info(f"{Fore.MAGENTA}---------- Test: {self._testMethodName} ----------{Style.RESET_ALL}")
        try:
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

    def test_multipart_upload_large_file(self):
        """Test multipart upload with a large file (20MB)"""
        logger.info(f"{Fore.MAGENTA}---------- Test: {self._testMethodName} ----------{Style.RESET_ALL}")
        try:
            # Create test file (20MB)
            object_name = 'multipart_large.dat'
            file_path = self._create_test_file(20, 'test_file_20mb.dat')
            logger.info(f"  {Fore.BLUE}1. Created test file: {file_path} (20MB){Style.RESET_ALL}")
            
            # Initialize multipart upload
            upload = self.client.init_multipart_upload(object_name)
            logger.info(f"  {Fore.BLUE}2. Initialized multipart upload with ID: {upload.upload_id}{Style.RESET_ALL}")
            
            # Upload parts
            start_time = time.time()
            with open(file_path, 'rb') as f:
                part_size = 5 * 1024 * 1024  # 5MB parts
                part_number = 1
                
                while True:
                    data = f.read(part_size)
                    if not data:
                        break
                        
                    etag = self.client.upload_part(upload, part_number, data)
                    upload.parts.append((part_number, etag))
                    logger.info(f"  {Fore.GREEN}3. Uploaded part {part_number}, ETag: {etag}{Style.RESET_ALL}")
                    part_number += 1
            
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

    def test_abort_multipart_upload(self):
        """Test aborting a multipart upload"""
        logger.info(f"{Fore.MAGENTA}---------- Test: {self._testMethodName} ----------{Style.RESET_ALL}")
        try:
            # Create test file
            object_name = 'multipart_abort.dat'
            file_path = self._create_test_file(10, 'test_file_10mb.dat')  # 10MB file
            logger.info(f"  {Fore.BLUE}1. Created test file: {file_path} (10MB){Style.RESET_ALL}")
            
            # Initialize multipart upload
            upload = self.client.init_multipart_upload(object_name)
            logger.info(f"  {Fore.BLUE}2. Initialized multipart upload with ID: {upload.upload_id}{Style.RESET_ALL}")
            
            # Upload first part
            with open(file_path, 'rb') as f:
                part_data = f.read(5 * 1024 * 1024)  # Read 5MB
                etag = self.client.upload_part(upload, 1, part_data)
                upload.parts.append((1, etag))
            logger.info(f"  {Fore.GREEN}3. Uploaded part 1, ETag: {etag}{Style.RESET_ALL}")
            
            # Abort the upload
            start_time = time.time()
            self.client.abort_multipart_upload(upload)
            abort_time = time.time() - start_time
            logger.info(f"  {Fore.GREEN}4. Multipart upload aborted{Style.RESET_ALL}")
            
            # Verify the file doesn't exist (should raise ObjectNotFoundError)
            try:
                self.client.download_file(object_name, os.path.join(self.temp_dir, 'should_not_exist.dat'))
                self.fail("File should not exist after abort")
            except ObjectNotFoundError:
                logger.info(f"  {Fore.GREEN}5. Verified file does not exist (expected){Style.RESET_ALL}")
                logger.info(f"Test {self._testMethodName} {Fore.GREEN}PASSED{Style.RESET_ALL}")
                return {
                    'name': self._testMethodName,
                    'result': 'PASSED',
                    'time': abort_time
                }
            except Exception as e:
                logger.error(f"Test {self._testMethodName} {Fore.RED}FAILED{Style.RESET_ALL}")
                logger.error(f"  {Fore.RED}- Unexpected exception: {str(e)}{Style.RESET_ALL}")
                logger.error(f"  {Fore.RED}- Traceback: {traceback.format_exc()}{Style.RESET_ALL}")
                return {
                    'name': self._testMethodName,
                    'result': 'FAILED',
                    'time': abort_time
                }
        except Exception as e:
            if not isinstance(e, ObjectNotFoundError):  # Skip logging if it's the expected error
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
    suite = unittest.TestLoader().loadTestsFromTestCase(TestAliyunMultipartUpload)
    runner = CustomTestRunner(verbosity=2)
    result = runner.run(suite)
    result.printReport()

if __name__ == '__main__':
    main() 