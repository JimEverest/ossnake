# Add project root directory to Python path
import sys
from pathlib import Path
project_root = str(Path(__file__).parent.parent)
sys.path.insert(0, project_root)

import unittest
import os
import tempfile
import json
import logging
import traceback
import time
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

class TestAliyunOSSClient(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Print test list before running any tests"""
        print(f"\n{Fore.CYAN}╔══════════════════════════════════════════════════════════════════╗{Style.RESET_ALL}")
        print(f"{Fore.CYAN}║                     Aliyun OSS Client Tests                      ║{Style.RESET_ALL}")
        print(f"{Fore.CYAN}��═══════════════════════════════════════════════════════════════��{Style.RESET_ALL}")
        
        test_methods = [m for m in dir(cls) if m.startswith('test_')]
        print(f"\n{Fore.YELLOW}Tests to be executed:{Style.RESET_ALL}")
        for i, method in enumerate(test_methods, 1):
            print(f"  {i}. {method}")
        print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")

    def setUp(self):
        logger.info(f"Setting up test: {self._testMethodName}")
        # Load config from config.json
        with open('config.json', 'r') as f:
            config_data = json.load(f)
            ali_config = config_data.get('aliyun', {})
            self.config = OSSConfig(**ali_config)

        # Create an instance of the client
        self.client = AliyunOSSClient(self.config)

        # Create a temporary directory for testing
        self.temp_dir = tempfile.mkdtemp()
        logger.info(f"  {Fore.CYAN}- Temporary directory created: {self.temp_dir}{Style.RESET_ALL}")

    def tearDown(self):
        logger.info(f"Tearing down test: {self._testMethodName}")
        # Clean up the temporary directory and delete uploaded files
        import shutil
        shutil.rmtree(self.temp_dir)
        logger.info(f"  {Fore.CYAN}- Temporary directory removed: {self.temp_dir}{Style.RESET_ALL}")
        try:
            logger.info(f"  {Fore.CYAN}- Deleting 'small_file.txt' from Aliyun OSS{Style.RESET_ALL}")
            self.client.delete_file('small_file.txt')
            logger.info(f"  {Fore.GREEN}- Deleted 'small_file.txt' from Aliyun OSS {Style.RESET_ALL}")
        except Exception as e:
            logger.info(f"  {Fore.RED}- Failed to delete 'small_file.txt' from Aliyun OSS: {e}{Style.RESET_ALL}")
        print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")
    
    def test_upload_download_file_small(self):
        logger.info(f"{Fore.MAGENTA}---------- Test: {self._testMethodName} ----------{Style.RESET_ALL}")
        try:
            # Create a small test file
            local_file = os.path.join(self.temp_dir, 'small_file.txt')
            with open(local_file, 'w') as f:
                f.write('This is a small test file.')
            logger.info(f"  {Fore.BLUE}1. Created local file: {local_file}{Style.RESET_ALL}")
            
            start_time = time.time()
            # Call the upload_file method
            logger.info(f"  {Fore.BLUE}2. Uploading file to Aliyun OSS: {local_file}{Style.RESET_ALL}")
            upload_url = self.client.upload_file(local_file, 'small_file.txt')
            upload_time = time.time() - start_time
            file_size = os.path.getsize(local_file)
            logger.info(f"  {Fore.GREEN}3. Upload completed, URL: {Fore.YELLOW}{upload_url}{Style.RESET_ALL}, Time: {Fore.YELLOW}{upload_time:.2f}s{Style.RESET_ALL}, Size: {Fore.YELLOW}{format_file_size(file_size)}{Style.RESET_ALL}")
            self.assertIsNotNone(upload_url)
            logger.info(f"  {Fore.GREEN}4. Verified upload URL{Style.RESET_ALL}")

            # Call the download_file method
            download_file = os.path.join(self.temp_dir, 'downloaded_file.txt')
            logger.info(f"  {Fore.BLUE}5. Downloading file from Aliyun OSS to: {download_file}{Style.RESET_ALL}")
            start_time = time.time()
            self.client.download_file('small_file.txt', download_file)
            download_time = time.time() - start_time
            logger.info(f"  {Fore.GREEN}6. Download completed, Time: {Fore.YELLOW}{download_time:.2f}s{Style.RESET_ALL}")

            # Assertions for download
            self.assertTrue(os.path.exists(download_file))
            with open(local_file, 'r') as original, open(download_file, 'r') as downloaded:
                self.assertEqual(original.read(), downloaded.read())
            logger.info(f"  {Fore.GREEN}7. Verified downloaded file content{Style.RESET_ALL}")
            logger.info(f"Test {self._testMethodName} {Fore.GREEN}PASSED{Style.RESET_ALL}")
            return {
                'name': self._testMethodName,
                'result': 'PASSED',
                'time': upload_time + download_time
            }
        except Exception as e:
            logger.error(f"Test {self._testMethodName} {Fore.RED}FAILED{Style.RESET_ALL}")
            logger.error(f"  {Fore.RED}- Exception: {e}{Style.RESET_ALL}")
            logger.error(f"  {Fore.RED}- Traceback: {traceback.format_exc()}{Style.RESET_ALL}")
            return {
                'name': self._testMethodName,
                'result': 'FAILED',
                'time': 0
            }
    
    def test_upload_download_large_file(self):
        logger.info(f"{Fore.MAGENTA}---------- Test: {self._testMethodName} ----------{Style.RESET_ALL}")
        try:
            # Create a large test file
            local_file = os.path.join(self.temp_dir, 'large_file.txt')
            with open(local_file, 'wb') as f:
                f.write(os.urandom(10 * 1024 * 1024))  # 10MB
            logger.info(f"  {Fore.BLUE}1. Created large local file: {local_file}{Style.RESET_ALL}")

            # Call the upload_file method
            start_time = time.time()
            logger.info(f"  {Fore.BLUE}2. Uploading large file to Aliyun OSS: {local_file}{Style.RESET_ALL}")
            upload_url = self.client.upload_file(local_file, 'large_file.txt')
            upload_time = time.time() - start_time
            file_size = os.path.getsize(local_file)
            logger.info(f"  {Fore.GREEN}3. Upload completed, URL: {Fore.YELLOW}{upload_url}{Style.RESET_ALL}, Time: {Fore.YELLOW}{upload_time:.2f}s{Style.RESET_ALL}, Size: {Fore.YELLOW}{format_file_size(file_size)}{Style.RESET_ALL}")
            self.assertIsNotNone(upload_url)
            logger.info(f"  {Fore.GREEN}4. Verified upload URL{Style.RESET_ALL}")

            # Call the download_file method
            download_file = os.path.join(self.temp_dir, 'downloaded_large_file.txt')
            logger.info(f"  {Fore.BLUE}5. Downloading large file from Aliyun OSS to: {download_file}{Style.RESET_ALL}")
            start_time = time.time()
            self.client.download_file('large_file.txt', download_file)
            download_time = time.time() - start_time
            logger.info(f"  {Fore.GREEN}6. Download completed, Time: {Fore.YELLOW}{download_time:.2f}s{Style.RESET_ALL}")

            # Assertions for download
            self.assertTrue(os.path.exists(download_file))
            self.assertEqual(os.path.getsize(local_file), os.path.getsize(download_file))
            logger.info(f"  {Fore.GREEN}7. Verified downloaded file size{Style.RESET_ALL}")
            logger.info(f"Test {self._testMethodName} {Fore.GREEN}PASSED{Style.RESET_ALL}")
            return {
                'name': self._testMethodName,
                'result': 'PASSED',
                'time': upload_time + download_time
            }
        except Exception as e:
            logger.error(f"Test {self._testMethodName} {Fore.RED}FAILED{Style.RESET_ALL}")
            logger.error(f"  {Fore.RED}- Exception: {e}{Style.RESET_ALL}")
            logger.error(f"  {Fore.RED}- Traceback: {traceback.format_exc()}{Style.RESET_ALL}")
            return {
                'name': self._testMethodName,
                'result': 'FAILED',
                'time': 0
            }

    def test_upload_file_with_content_type(self):
        logger.info(f"{Fore.MAGENTA}---------- Test: {self._testMethodName} ----------{Style.RESET_ALL}")
        try:
            # Create a small test file
            local_file = os.path.join(self.temp_dir, 'test.json')
            with open(local_file, 'w') as f:
                json.dump({'test': 'data'}, f)
            logger.info(f"  {Fore.BLUE}1. Created local file: {local_file}{Style.RESET_ALL}")

            # Call the upload_file method with content type
            logger.info(f"  {Fore.BLUE}2. Uploading file with content type to Aliyun OSS: {local_file}{Style.RESET_ALL}")
            start_time = time.time()  # Define start_time here
            upload_url = self.client.upload_file(local_file, 'test.json', content_type='application/json')
            upload_time = time.time() - start_time
            file_size = os.path.getsize(local_file)
            logger.info(f"  {Fore.GREEN}3. Upload completed, URL: {Fore.YELLOW}{upload_url}{Style.RESET_ALL}, Time: {Fore.YELLOW}{upload_time:.2f}s{Style.RESET_ALL}, Size: {Fore.YELLOW}{format_file_size(file_size)}{Style.RESET_ALL}")
            self.assertIsNotNone(upload_url)
            logger.info(f"  {Fore.GREEN}4. Verified upload URL{Style.RESET_ALL}")

            # Call the download_file method
            download_file = os.path.join(self.temp_dir, 'downloaded_test.json')
            logger.info(f"  {Fore.BLUE}5. Downloading file from Aliyun OSS to: {download_file}{Style.RESET_ALL}")
            start_time = time.time()
            self.client.download_file('test.json', download_file)
            download_time = time.time() - start_time
            logger.info(f"  {Fore.GREEN}6. Download completed, Time: {Fore.YELLOW}{download_time:.2f}s{Style.RESET_ALL}")

            # Assertions for download
            self.assertTrue(os.path.exists(download_file))
            with open(local_file, 'r') as original, open(download_file, 'r') as downloaded:
                self.assertEqual(json.load(original), json.load(downloaded))
            logger.info(f"  {Fore.GREEN}7. Verified downloaded file content{Style.RESET_ALL}")
            logger.info(f"Test {self._testMethodName} {Fore.GREEN}PASSED{Style.RESET_ALL}")
            return {
                'name': self._testMethodName,
                'result': 'PASSED',
                'time': upload_time + download_time
            }
        except Exception as e:
            logger.error(f"Test {self._testMethodName} {Fore.RED}FAILED{Style.RESET_ALL}")
            logger.error(f"  {Fore.RED}- Exception: {e}{Style.RESET_ALL}")
            logger.error(f"  {Fore.RED}- Traceback: {traceback.format_exc()}{Style.RESET_ALL}")
            return {
                'name': self._testMethodName,
                'result': 'FAILED',
                'time': 0
            }

    def test_invalid_credentials(self):
        logger.info(f"{Fore.MAGENTA}---------- Test: {self._testMethodName} ----------{Style.RESET_ALL}")
        try:
            # Create a dummy config with invalid credentials
            invalid_config = OSSConfig(
                endpoint= self.config.endpoint,
                access_key= "invalid_access_key",
                secret_key= "invalid_secret_key",
                bucket_name= self.config.bucket_name,
                region= self.config.region,
                secure= self.config.secure,
                proxy= self.config.proxy
            )
            invalid_client = AliyunOSSClient(invalid_config)
            logger.info(f"  {Fore.BLUE}1. Created client with invalid credentials{Style.RESET_ALL}")

            # Create a small test file
            local_file = os.path.join(self.temp_dir, 'small_file.txt')
            with open(local_file, 'w') as f:
                f.write('This is a small test file.')
            logger.info(f"  {Fore.BLUE}2. Created local file: {local_file}{Style.RESET_ALL}")

            # Call the upload_file method and assert AuthenticationError
            logger.info(f"  {Fore.BLUE}3. Attempting upload with invalid credentials{Style.RESET_ALL}")
            with self.assertRaises(UploadError) as context:
                invalid_client.upload_file(local_file, 'small_file.txt')
            self.assertIsInstance(context.exception, UploadError)
            self.assertIsInstance(context.exception.__cause__, AuthenticationError)
            logger.info(f"  {Fore.GREEN}4. Verified AuthenticationError was raised{Style.RESET_ALL}")
            logger.info(f"Test {self._testMethodName} {Fore.GREEN}PASSED{Style.RESET_ALL}")
            return {
                'name': self._testMethodName,
                'result': 'PASSED',
                'time': 0
            }
        except Exception as e:
            logger.error(f"Test {self._testMethodName} {Fore.RED}FAILED{Style.RESET_ALL}")
            logger.error(f"  {Fore.RED}- Exception: {e}{Style.RESET_ALL}")
            logger.error(f"  {Fore.RED}- Traceback: {traceback.format_exc()}{Style.RESET_ALL}")
            return {
                'name': self._testMethodName,
                'result': 'FAILED',
                'time': 0
            }

class CustomTestResult(unittest.TestResult):
    def __init__(self, stream=None, descriptions=None, verbosity=None):
        super().__init__(stream, descriptions, verbosity)
        self.test_results = []
        self.start_time = time.time()
        self.current_test = None
        self.current_test_start = None
        
    def startTest(self, test):
        self.current_test = test
        self.current_test_start = time.time()
        super().startTest(test)
        
    def stopTest(self, test):
        elapsed_time = time.time() - self.current_test_start
        # 通过检查failures和errors来确定测试是否通过
        test_id = test.id().split('.')[-1]
        is_passed = True
        for failure in self.failures:
            if failure[0].id().split('.')[-1] == test_id:
                is_passed = False
                break
        for error in self.errors:
            if error[0].id().split('.')[-1] == test_id:
                is_passed = False
                break
        
        self.test_results.append({
            'name': test_id,
            'result': 'PASSED' if is_passed else 'FAILED',
            'time': elapsed_time
        })
        super().stopTest(test)

    def printReport(self):
        # Print detailed test report
        print(f"\n{Fore.CYAN}╔══════════════════════════════════════════════════════════════╗{Style.RESET_ALL}")
        print(f"{Fore.CYAN}║                        Test Report                           ║{Style.RESET_ALL}")
        print(f"{Fore.CYAN}��══════════════════════════════════════════════════════════════╝{Style.RESET_ALL}\n")
        
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
        print(f"{Fore.CYAN}║                     Aliyun OSS Client Tests                      ║{Style.RESET_ALL}")
        print(f"{Fore.CYAN}��══════════════════════════════════════════════════════════════╝{Style.RESET_ALL}")
        
        # Print test list
        test_methods = [m for m in dir(TestAliyunOSSClient) if m.startswith('test_')]
        print(f"\n{Fore.YELLOW}Tests to be executed:{Style.RESET_ALL}")
        for i, method in enumerate(test_methods, 1):
            print(f"  {i}. {method}")
        print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")

        result = super().run(test)
        result.printReport()
        return result

def main():
    # Create and run test suite
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TestAliyunOSSClient))
    
    runner = CustomTestRunner(verbosity=2)
    runner.run(suite)

if __name__ == '__main__':
    main() 