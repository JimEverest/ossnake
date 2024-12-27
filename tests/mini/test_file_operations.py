import sys
from pathlib import Path
project_root = str(Path(__file__).parent.parent.parent)
sys.path.insert(0, project_root)

import unittest
import os
import json
import logging
import time
from datetime import datetime
from colorama import Fore, Style, init
from driver.minio_client import MinioClient
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

class TestMinioFileOperations(unittest.TestCase):
    """测试MinIO文件操作"""
    
    def setUp(self):
        """测试初始化"""
        # 加载配置
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
            self.config = OSSConfig(**config['minio'])
        
        self.client = MinioClient(self.config)
        self.test_file = 'large_file.txt'
        
        # 确保测试文件存在
        if not self.client.object_exists(self.test_file):
            raise FileNotFoundError(f"Test file not found: {self.test_file}")
            
        logger.info(f"Test file size: {SizeFormatter.format_size(self.client.get_object_size(self.test_file))}")
    
    def test_1_copy_file(self):
        """测试文件复制"""
        source_key = self.test_file
        target_key = 'copy_test/large_file_copy.txt'
        
        try:
            # 执行复制
            start_time = time.time()
            new_url = self.client.copy_object(source_key, target_key)
            copy_time = time.time() - start_time
            
            # 验证复制结果
            self.assertTrue(self.client.object_exists(target_key))
            source_size = self.client.get_object_size(source_key)
            target_size = self.client.get_object_size(target_key)
            self.assertEqual(source_size, target_size)
            
            logger.info(f"File copied successfully:")
            logger.info(f"  • Source: {source_key}")
            logger.info(f"  • Target: {target_key}")
            logger.info(f"  • Size: {SizeFormatter.format_size(target_size)}")
            logger.info(f"  • Time: {copy_time:.2f}s")
            logger.info(f"  • URL: {new_url}")
            
        finally:
            # 清理测试文件
            if self.client.object_exists(target_key):
                self.client.delete_file(target_key)
    
    def test_2_rename_file(self):
        """测试文件重命名"""
        source_key = self.test_file
        target_key = 'rename_test/large_file_renamed.txt'
        
        try:
            # 先复制一个测试文件
            self.client.copy_object(source_key, 'temp_test_file.txt')
            
            # 执行重命名
            start_time = time.time()
            new_url = self.client.rename_object('temp_test_file.txt', target_key)
            rename_time = time.time() - start_time
            
            # 验证重命名结果
            self.assertFalse(self.client.object_exists('temp_test_file.txt'))
            self.assertTrue(self.client.object_exists(target_key))
            
            logger.info(f"File renamed successfully:")
            logger.info(f"  • Source: temp_test_file.txt")
            logger.info(f"  • Target: {target_key}")
            logger.info(f"  • Time: {rename_time:.2f}s")
            logger.info(f"  • URL: {new_url}")
            
        finally:
            # 清理测试文件
            if self.client.object_exists(target_key):
                self.client.delete_file(target_key)
    
    def test_3_rename_folder(self):
        """测试文件夹重命名"""
        source_prefix = 'test_folder/'
        target_prefix = 'renamed_folder/'
        
        try:
            # 创建测试文件夹结构
            test_files = [
                'test_folder/file1.txt',
                'test_folder/file2.txt',
                'test_folder/subfolder/file3.txt'
            ]
            
            # 复制文件到测试文件夹
            for file_path in test_files:
                self.client.copy_object(self.test_file, file_path)
            
            # 执行文件夹重命名
            start_time = time.time()
            self.client.rename_folder(source_prefix, target_prefix)
            rename_time = time.time() - start_time
            
            # 验证重命名结果
            for file_path in test_files:
                old_path = file_path
                new_path = file_path.replace(source_prefix, target_prefix)
                self.assertFalse(self.client.object_exists(old_path))
                self.assertTrue(self.client.object_exists(new_path))
            
            logger.info(f"Folder renamed successfully:")
            logger.info(f"  • Source: {source_prefix}")
            logger.info(f"  • Target: {target_prefix}")
            logger.info(f"  • Files: {len(test_files)}")
            logger.info(f"  • Time: {rename_time:.2f}s")
            
        finally:
            # 清理测试文件
            for file_path in test_files:
                new_path = file_path.replace(source_prefix, target_prefix)
                if self.client.object_exists(new_path):
                    self.client.delete_file(new_path)

def main():
    suite = unittest.TestLoader().loadTestsFromTestCase(TestMinioFileOperations)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # 等待用户按键后退出
    input("\nPress Enter to exit...")

if __name__ == '__main__':
    main() 