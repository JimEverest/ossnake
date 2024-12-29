# utils/config_manager.py
# 实现一个配置管理器，用于管理多个OSS源的配置，包括添加、编辑和删除。
import json
import os
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Dict
from driver.base_oss import BaseOSSClient
from driver.aws_s3 import AWSS3Client
from driver.oss_ali import AliyunOSSClient
from driver.minio_client import MinioClient
from driver.types import OSSConfig

class ConfigManager:
    CONFIG_FILE = "config.json"
    TIMEOUT = 30  # 超时时间（秒）
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        if not os.path.exists(self.CONFIG_FILE):
            self.save_config({})
        # 初始化时就加载客户端
        self.oss_clients = self.load_clients()
    
    def _init_client_with_timeout(self, client_class, config) -> tuple:
        """在超时限制内初始化客户端"""
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(client_class, config)
            try:
                client = future.result(timeout=self.TIMEOUT)
                return True, client
            except TimeoutError:
                self.logger.error(f"Client initialization timed out after {self.TIMEOUT} seconds")
                return False, None
            except Exception as e:
                self.logger.error(f"Failed to initialize client: {str(e)}")
                return False, None
    
    def load_clients(self) -> Dict:
        """从配置文件加载所有OSS客户端"""
        config = self.load_config()
        clients = {}
        
        # 处理AWS S3配置
        if 'aws' in config:
            aws_config = config['aws'].copy()
            aws_config['provider'] = 'aws_s3'
            if 'endpoint' not in aws_config:
                aws_config['endpoint'] = None
            
            success, client = self._init_client_with_timeout(
                AWSS3Client,
                OSSConfig(**aws_config)
            )
            if success:
                clients['aws'] = client
                self.logger.info("AWS S3 client loaded successfully")
        
        # 处理阿里云OSS配置
        if 'aliyun' in config:
            aliyun_config = config['aliyun'].copy()
            aliyun_config['provider'] = 'oss_ali'
            
            success, client = self._init_client_with_timeout(
                AliyunOSSClient,
                OSSConfig(**aliyun_config)
            )
            if success:
                clients['aliyun'] = client
                self.logger.info("Aliyun OSS client loaded successfully")
        
        # 处理MinIO配置
        if 'minio' in config:
            minio_config = config['minio'].copy()
            minio_config['provider'] = 'minio'
            
            success, client = self._init_client_with_timeout(
                MinioClient,
                OSSConfig(**minio_config)
            )
            if success:
                clients['minio'] = client
                self.logger.info("MinIO client loaded successfully")
        
        return clients
    
    def load_config(self):
        try:
            with open(self.CONFIG_FILE, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            self.logger.error(f"Config file not found: {self.CONFIG_FILE}")
            return {}
        except json.JSONDecodeError:
            self.logger.error(f"Error decoding config file: {self.CONFIG_FILE}")
            return {}
    
    def save_config(self, config):
        with open(self.CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
    
    def add_client(self, name: str, config: dict):
        config_data = self.load_config()
        config_data.setdefault("oss_clients", {})[name] = config
        self.save_config(config_data)
    
    def remove_client(self, name: str):
        config_data = self.load_config()
        if name in config_data.get("oss_clients", {}):
            del config_data["oss_clients"][name]
            self.save_config(config_data)
    
    def reload_clients(self):
        """重新加载所有OSS客户端"""
        try:
            # 重新加载客户端
            new_clients = self.load_clients()
            
            # 如果成功加载了新的客户端，更新当前的客户端列表
            self.oss_clients = new_clients
            
            # 如果有主窗口引用，更新UI
            if hasattr(self, 'main_window'):
                self.main_window.update_oss_clients(self.oss_clients)
                
            self.logger.info("Successfully reloaded OSS clients")
            
        except Exception as e:
            self.logger.error(f"Failed to reload clients: {e}")
            raise
    
    # 添加编辑功能
