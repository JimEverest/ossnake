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
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from colorama import Fore, Style, init
from driver.minio_client import MinioClient
from driver.types import OSSConfig, ProgressCallback
from driver.exceptions import *
from tests.utils import SizeFormatter, ConcurrentProgressTracker
from io import BytesIO

# Initialize colorama
init(autoreset=True)

# Configure logging
log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
logging.getLogger('minio').setLevel(logging.DEBUG)

class TestMinioE2E(unittest.TestCase):
    """End-to-End Tests for MinIO"""

    @classmethod
    def setUpClass(cls):
        """Print test list before running any tests"""
        print(f"\n{Fore.CYAN}╔════════���═══════�������═════════════════════════════════════════════╗{Style.RESET_ALL}")
        print(f"{Fore.CYAN}║             MinIO End-to-End Tests                       ║{Style.RESET_ALL}")
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

        # Create an instance of the client
        self.client = MinioClient(self.config)

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
        print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")

    def _create_test_file(self, size_mb: int, filename: str = None) -> str:
        """Create a test file of specified size in MB"""
        if filename is None:
            filename = f'test_file_{size_mb}mb.dat'
        file_path = os.path.join(self.temp_dir, filename)
        
        # Create file with random data
        with open(file_path, 'wb') as f:
            f.write(os.urandom(size_mb * 1024 * 1024))
        
        return file_path

    def test_01_basic_operations(self):
        """Test basic upload, download, delete, list, presigned URL, public URL"""
        logger.info(f"{Fore.MAGENTA}---------- Test: {self._testMethodName} ----------{Style.RESET_ALL}")
        try:
            # 1. Upload
            object_name = 'basic_ops.txt'
            file_path = self._create_test_file(1, object_name)
            self.client.upload_file(file_path, object_name)
            logger.info(f"  {Fore.BLUE}1. Uploaded file: {self.client.get_public_url(object_name)}{Style.RESET_ALL}")

            # 2. Download and Verify
            download_path = os.path.join(self.temp_dir, 'downloaded_basic_ops.txt')
            self.client.download_file(object_name, download_path)
            self.assertEqual(os.path.getsize(file_path), os.path.getsize(download_path))
            logger.info(f"  {Fore.GREEN}2. Downloaded and verified file{Style.RESET_ALL}")

            # 3. List Objects and Verify
            objects = self.client.list_objects()
            self.assertTrue(any(obj['name'] == object_name for obj in objects))
            logger.info(f"  {Fore.GREEN}3. Listed and verified object{Style.RESET_ALL}")

            # 4. Presigned URL
            presigned_url = self.client.get_presigned_url(object_name, expires=timedelta(hours=1))
            logger.info(f"  {Fore.BLUE}4. Generated presigned URL: {presigned_url}{Style.RESET_ALL}")

            # 5. Public URL
            public_url = self.client.get_public_url(object_name)
            logger.info(f"  {Fore.BLUE}5. Got public URL: {public_url}{Style.RESET_ALL}")

            # 6. Delete and Verify
            self.client.delete_file(object_name)
            with self.assertRaises(ObjectNotFoundError):
                self.client.download_file(object_name, download_path)
            logger.info(f"  {Fore.GREEN}6. Deleted and verified file deletion{Style.RESET_ALL}")

        except Exception as e:
            logger.error(f"Test {self._testMethodName} {Fore.RED}FAILED{Style.RESET_ALL}")
            logger.error(f"  {Fore.RED}- Exception: {str(e)}{Style.RESET_ALL}")
            logger.error(f"  {Fore.RED}- Traceback: {traceback.format_exc()}{Style.RESET_ALL}")
            self.fail(f"Test {self._testMethodName} failed: {str(e)}")

    def test_02_error_handling(self):
        """Test error handling for various scenarios"""
        logger.info(f"{Fore.MAGENTA}---------- Test: {self._testMethodName} ----------{Style.RESET_ALL}")
        try:
            # 1. Non-existent File Download
            with self.assertRaises(ObjectNotFoundError):
                self.client.download_file('non_existent_file.txt', os.path.join(self.temp_dir, 'download.dat'))
            logger.info(f"  {Fore.GREEN}1. Verified ObjectNotFoundError for non-existent file download{Style.RESET_ALL}")

            # 2. Non-existent File Deletion - Test this before modifying credentials
            with self.assertRaises(ObjectNotFoundError):
                self.client.delete_file('non_existent_file.txt')
            logger.info(f"  {Fore.GREEN}2. Verified ObjectNotFoundError for non-existent file deletion{Style.RESET_ALL}")

            # 3. Invalid Credentials
            original_access_key = self.config.access_key
            self.config.access_key = 'wrong_key'
            self.client = MinioClient(self.config)
            with self.assertRaises(Exception) as context:  # Catch broader exception
                self.client.list_objects()

            self.config.access_key = original_access_key
            self.client = MinioClient(self.config)

            # Check if specific error messages are in the exception
            error_message = str(context.exception).lower()
            self.assertTrue('invalidaccesskeyid' in error_message or 'access denied' in error_message or 'invalid credentials' in error_message or 'authentication' in error_message,
                            "Expected an authentication-related error message")

            logger.info(f"  {Fore.GREEN}3. Verified ConnectionError or AuthenticationError for invalid credentials{Style.RESET_ALL}")

        except Exception as e:
            logger.error(f"Test {self._testMethodName} {Fore.RED}FAILED{Style.RESET_ALL}")
            logger.error(f"  {Fore.RED}- Exception: {str(e)}{Style.RESET_ALL}")
            logger.error(f"  {Fore.RED}- Traceback: {traceback.format_exc()}{Style.RESET_ALL}")
            self.fail(f"Test {self._testMethodName} failed: {str(e)}")

    def test_03_concurrent_operations(self):
        """Test concurrent uploads and downloads"""
        logger.info(f"{Fore.MAGENTA}---------- Test: {self._testMethodName} ----------{Style.RESET_ALL}")
        try:
            # 1. Concurrent Uploads
            num_files = 5
            file_size = 3  # MB
            logger.info(f"  {Fore.BLUE}1. Starting concurrent uploads...{Style.RESET_ALL}")
            with ThreadPoolExecutor(max_workers=num_files) as executor:
                futures = []
                for i in range(num_files):
                    object_name = f'concurrent_upload_{i}.dat'
                    file_path = self._create_test_file(file_size, object_name)
                    future = executor.submit(self.client.upload_file, file_path, object_name)
                    futures.append((future, object_name))

                for future, object_name in futures:
                    future.result()
                    logger.info(f"  {Fore.GREEN}- Uploaded: {object_name}{Style.RESET_ALL}")
            logger.info(f"  {Fore.GREEN}2. Concurrent uploads completed{Style.RESET_ALL}")

            # 2. Concurrent Downloads
            logger.info(f"  {Fore.BLUE}3. Starting concurrent downloads...{Style.RESET_ALL}")
            with ThreadPoolExecutor(max_workers=num_files) as executor:
                futures = []
                for i in range(num_files):
                    object_name = f'concurrent_upload_{i}.dat'
                    download_path = os.path.join(self.temp_dir, f'downloaded_concurrent_{i}.dat')
                    future = executor.submit(self.client.download_file, object_name, download_path)
                    futures.append((future, object_name, download_path))

                for future, object_name, download_path in futures:
                    future.result()
                    logger.info(f"  {Fore.GREEN}- Downloaded: {object_name}{Style.RESET_ALL}")

            # 3. Verify Downloads
            for i in range(num_files):
                original_file = f'concurrent_upload_{i}.dat'
                downloaded_file = os.path.join(self.temp_dir, f'downloaded_concurrent_{i}.dat')
                self.assertEqual(os.path.getsize(os.path.join(self.temp_dir, original_file)), os.path.getsize(downloaded_file))
            logger.info(f"  {Fore.GREEN}4. Verified concurrent downloads{Style.RESET_ALL}")

            # 4. Concurrent Deletions
            logger.info(f"  {Fore.BLUE}5. Starting concurrent deletions...{Style.RESET_ALL}")
            with ThreadPoolExecutor(max_workers=num_files) as executor:
                futures = []
                for i in range(num_files):
                    object_name = f'concurrent_upload_{i}.dat'
                    future = executor.submit(self.client.delete_file, object_name)
                    futures.append((future, object_name))

                for future, object_name in futures:
                    future.result()
                    logger.info(f"  {Fore.GREEN}- Deleted: {object_name}{Style.RESET_ALL}")
            logger.info(f"  {Fore.GREEN}6. Concurrent deletions completed{Style.RESET_ALL}")

        except Exception as e:
            logger.error(f"Test {self._testMethodName} {Fore.RED}FAILED{Style.RESET_ALL}")
            logger.error(f"  {Fore.RED}- Exception: {str(e)}{Style.RESET_ALL}")
            logger.error(f"  {Fore.RED}- Traceback: {traceback.format_exc()}{Style.RESET_ALL}")
            self.fail(f"Test {self._testMethodName} failed: {str(e)}")

    def test_04_large_file_multipart_upload(self):
        """Test multipart upload for a large file"""
        logger.info(f"{Fore.MAGENTA}---------- Test: {self._testMethodName} ----------{Style.RESET_ALL}")
        try:
            # 1. Initialize Upload
            object_name = 'large_file_multipart.dat'
            upload = self.client.init_multipart_upload(object_name)
            logger.info(f"  {Fore.BLUE}1. Initialized multipart upload: {upload.upload_id}{Style.RESET_ALL}")
            
            # Create a test file (20MB)
            file_path = self._create_test_file(40)
            logger.debug(f"Created test file: {file_path}, size: {os.path.getsize(file_path)}")
            
            # Split file into parts (5MB each)
            part_size = 5 * 1024 * 1024  # 5MB
            parts = []
            
            with open(file_path, 'rb') as f:
                part_number = 1
                while True:
                    data = f.read(part_size)
                    if not data:
                        break
                    
                    logger.debug(f"Reading part {part_number}, size: {len(data)}")
                    
                    # Upload part
                    etag = self.client.upload_part(upload, part_number, data)
                    parts.append((part_number, etag))
                    logger.info(f"  {Fore.BLUE}2. Uploaded part {part_number}, ETag: {etag}{Style.RESET_ALL}")
                    part_number += 1
                    
            # Add parts to upload object
            upload.parts = parts

            # Complete Multipart Upload
            result_url = self.client.complete_multipart_upload(upload)
            logger.info(f"  {Fore.GREEN}3. Multipart upload completed: {result_url}{Style.RESET_ALL}")

            # Download and Verify
            download_path = os.path.join(self.temp_dir, 'downloaded_large_file.dat')
            self.client.download_file(object_name, download_path)
            self.assertEqual(os.path.getsize(file_path), os.path.getsize(download_path))
            logger.info(f"  {Fore.GREEN}4. Downloaded and verified large file{Style.RESET_ALL}")

            # Clean Up
            self.client.delete_file(object_name)
            logger.info(f"  {Fore.BLUE}5. Cleaned up large file{Style.RESET_ALL}")

        except Exception as e:
            logger.error(f"Test {self._testMethodName} {Fore.RED}FAILED{Style.RESET_ALL}")
            logger.error(f"  {Fore.RED}- Exception: {str(e)}{Style.RESET_ALL}")
            logger.error(f"  {Fore.RED}- Traceback: {traceback.format_exc()}{Style.RESET_ALL}")
            self.fail(f"Test {self._testMethodName} failed: {str(e)}")

    def test_05_proxy_operations(self):
        """Test upload and download through a proxy"""
        logger.info(f"{Fore.MAGENTA}---------- Test: {self._testMethodName} ----------{Style.RESET_ALL}")
        try:
            # 1. Configure Proxy
            proxy_url = "http://127.0.0.1:33210"  # Replace with your proxy URL
            self.config.proxy = proxy_url
            self.client = MinioClient(self.config)
            logger.info(f"  {Fore.BLUE}1. Configured proxy: {proxy_url}{Style.RESET_ALL}")

            # 2. Upload Through Proxy
            object_name = 'proxy_upload.dat'
            file_path = self._create_test_file(5, object_name)
            self.client.upload_file(file_path, object_name)
            logger.info(f"  {Fore.GREEN}2. Uploaded file through proxy: {self.client.get_public_url(object_name)}{Style.RESET_ALL}")

            # 3. Download Through Proxy and Verify
            download_path = os.path.join(self.temp_dir, 'downloaded_proxy.dat')
            self.client.download_file(object_name, download_path)
            self.assertEqual(os.path.getsize(file_path), os.path.getsize(download_path))
            logger.info(f"  {Fore.GREEN}3. Downloaded and verified file through proxy{Style.RESET_ALL}")

            # 4. Clean Up
            self.client.delete_file(object_name)
            logger.info(f"  {Fore.BLUE}4. Cleaned up file uploaded through proxy{Style.RESET_ALL}")

        except Exception as e:
            logger.error(f"Test {self._testMethodName} {Fore.RED}FAILED{Style.RESET_ALL}")
            logger.error(f"  {Fore.RED}- Exception: {str(e)}{Style.RESET_ALL}")
            logger.error(f"  {Fore.RED}- Traceback: {traceback.format_exc()}{Style.RESET_ALL}")
            self.fail(f"Test {self._testMethodName} failed: {str(e)}")

    def test_06_copy_rename_operations(self):
        """Test copy and rename operations for objects and folders"""
        logger.info(f"{Fore.MAGENTA}---------- Test: {self._testMethodName} ----------{Style.RESET_ALL}")
        try:
            # 1. Copy Object
            source_object = 'source_object.txt'
            copied_object = 'copied_object.txt'
            file_path = self._create_test_file(1, source_object)
            self.client.upload_file(file_path, source_object)
            self.client.copy_object(source_object, copied_object)
            logger.info(f"  {Fore.BLUE}1. Copied object: {source_object} to {copied_object}{Style.RESET_ALL}")

            # Verify Copy
            self.assertTrue(self.client.object_exists(copied_object))
            logger.info(f"  {Fore.GREEN}2. Verified copied object exists{Style.RESET_ALL}")

            # 2. Rename Object
            renamed_object = 'renamed_object.txt'
            self.client.rename_object(copied_object, renamed_object)
            logger.info(f"  {Fore.BLUE}3. Renamed object: {copied_object} to {renamed_object}{Style.RESET_ALL}")

            # Verify Rename
            self.assertFalse(self.client.object_exists(copied_object))
            self.assertTrue(self.client.object_exists(renamed_object))
            logger.info(f"  {Fore.GREEN}4. Verified renamed object exists{Style.RESET_ALL}")

            # 3. Create Folder and Files for Folder Rename
            folder_prefix = 'test_folder/'
            files_in_folder = [
                f'{folder_prefix}file1.txt',
                f'{folder_prefix}file2.txt',
                f'{folder_prefix}subfolder/file3.txt'
            ]
            for file_path in files_in_folder:
                self.client.upload_file(self._create_test_file(1, file_path.split('/')[-1]), file_path)
            logger.info(f"  {Fore.BLUE}5. Created folder and files for folder rename test{Style.RESET_ALL}")

            # 4. Rename Folder
            new_folder_prefix = 'renamed_folder/'
            self.client.rename_folder(folder_prefix, new_folder_prefix)
            logger.info(f"  {Fore.GREEN}6. Renamed folder: {folder_prefix} to {new_folder_prefix}{Style.RESET_ALL}")

            # Verify Folder Rename
            for file_path in files_in_folder:
                old_path = file_path
                new_path = file_path.replace(folder_prefix, new_folder_prefix)
                self.assertFalse(self.client.object_exists(old_path))
                self.assertTrue(self.client.object_exists(new_path))
            logger.info(f"  {Fore.GREEN}7. Verified renamed folder and files{Style.RESET_ALL}")

            # Clean Up
            self.client.delete_file(source_object)
            self.client.delete_file(renamed_object)
            for file_path in files_in_folder:
                new_path = file_path.replace(folder_prefix, new_folder_prefix)
                self.client.delete_file(new_path)
            logger.info(f"  {Fore.BLUE}8. Cleaned up objects and folders{Style.RESET_ALL}")

        except Exception as e:
            logger.error(f"Test {self._testMethodName} {Fore.RED}FAILED{Style.RESET_ALL}")
            logger.error(f"  {Fore.RED}- Exception: {str(e)}{Style.RESET_ALL}")
            logger.error(f"  {Fore.RED}- Traceback: {traceback.format_exc()}{Style.RESET_ALL}")
            self.fail(f"Test {self._testMethodName} failed: {str(e)}")

    def test_07_object_exists_and_size(self):
        """Test checking object existence and getting object size"""
        logger.info(f"{Fore.MAGENTA}---------- Test: {self._testMethodName} ----------{Style.RESET_ALL}")
        try:
            # Create a test file and upload
            object_name = 'existence_size_test.txt'
            file_path = self._create_test_file(2, object_name)
            self.client.upload_file(file_path, object_name)
            logger.info(f"  {Fore.BLUE}1. Uploaded test file for existence and size check{Style.RESET_ALL}")

            # Check if the object exists
            self.assertTrue(self.client.object_exists(object_name))
            logger.info(f"  {Fore.GREEN}2. Verified object exists{Style.RESET_ALL}")

            # Get object size and verify
            size = self.client.get_object_size(object_name)
            self.assertEqual(size, os.path.getsize(file_path))
            logger.info(f"  {Fore.GREEN}3. Verified object size: {size} bytes{Style.RESET_ALL}")

            # Check for a non-existent object
            self.assertFalse(self.client.object_exists('non_existent_object.txt'))
            logger.info(f"  {Fore.GREEN}4. Verified non-existent object does not exist{Style.RESET_ALL}")

            # Clean up
            self.client.delete_file(object_name)
            logger.info(f"  {Fore.BLUE}5. Cleaned up test file{Style.RESET_ALL}")

        except Exception as e:
            logger.error(f"Test {self._testMethodName} {Fore.RED}FAILED{Style.RESET_ALL}")
            logger.error(f"  {Fore.RED}- Exception: {str(e)}{Style.RESET_ALL}")
            logger.error(f"  {Fore.RED}- Traceback: {traceback.format_exc()}{Style.RESET_ALL}")
            self.fail(f"Test {self._testMethodName} failed: {str(e)}")

def main():
    suite = unittest.TestLoader().loadTestsFromTestCase(TestMinioE2E)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # 等待用户按键后退出
    input("\nPress Enter to exit...")

if __name__ == '__main__':
    main()
