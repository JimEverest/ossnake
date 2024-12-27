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
from colorama import Fore, Style, init
from driver.aws_s3 import AWSS3Client
from driver.types import OSSConfig
from tests.utils import SizeFormatter

# Initialize colorama
init(autoreset=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TestAWSProxyUpload(unittest.TestCase):
    """测试AWS通过代理上传文件"""
    
    def setUp(self):
        """测试初始化"""
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
            self.config = OSSConfig(**config['aws'])
        
        # 添加代理配置
        self.config.proxy = "http://127.0.0.1:33210"
        
        self.client = AWSS3Client(self.config)
        self.temp_dir = tempfile.mkdtemp()
        
    def _create_test_file(self, size_mb: int) -> str:
        """创建测试文件"""
        file_path = os.path.join(self.temp_dir, f'test_file_{size_mb}mb.dat')
        
        logger.info(f"Creating test file: {file_path}")
        logger.info(f"  • Size: {size_mb}MB")
        
        start_time = time.time()
        with open(file_path, 'wb') as f:
            f.write(os.urandom(size_mb * 1024 * 1024))
            
        creation_time = time.time() - start_time
        logger.info(f"  • Creation Time: {creation_time:.2f}s")
        return file_path

    def test_proxy_upload(self):
        """测试通过代理上传文件"""
        try:
            # 1. 创建测试文件
            file_size = 10  # 10MB
            file_path = self._create_test_file(file_size)
            
            # 2. 上传文件
            object_name = 'proxy_test.dat'
            start_time = time.time()
            
            def progress_callback(transferred: int, total: int):
                progress = (transferred / total) * 100
                speed = transferred / (time.time() - start_time)
                logger.info(
                    f"Progress: {progress:.1f}% "
                    f"({SizeFormatter.format_size(transferred)}/"
                    f"{SizeFormatter.format_size(total)}) "
                    f"- {SizeFormatter.format_size(speed)}/s"
                )
            
            url = self.client.upload_file(
                file_path,
                object_name,
                progress_callback=progress_callback
            )
            
            upload_time = time.time() - start_time
            
            # 3. 输出结果
            logger.info(f"\n{Fore.GREEN}Upload successful:{Style.RESET_ALL}")
            logger.info(f"  • File: {file_path}")
            logger.info(f"  • Size: {SizeFormatter.format_size(file_size * 1024 * 1024)}")
            logger.info(f"  • Time: {upload_time:.2f}s")
            logger.info(f"  • Speed: {SizeFormatter.format_size(file_size * 1024 * 1024 / upload_time)}/s")
            logger.info(f"  • URL: {url}")
            logger.info(f"  • Proxy: {self.config.proxy}")
            
            # 4. 清理
            os.unlink(file_path)
            self.client.delete_file(object_name)
            
        except Exception as e:
            logger.error(f"Upload failed: {str(e)}")
            raise

def main():
    suite = unittest.TestLoader().loadTestsFromTestCase(TestAWSProxyUpload)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    input("\nPress Enter to exit...")

if __name__ == '__main__':
    main()
