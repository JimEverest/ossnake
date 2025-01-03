# utils/config_manager.py
# 实现一个配置管理器，用于管理多个OSS源的配置，包括添加、编辑和删除。
import json
import os
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Dict, Optional, List
from driver.base_oss import BaseOSSClient
from driver.aws_s3 import AWSS3Client
from driver.oss_ali import AliyunOSSClient
from driver.minio_client import MinioClient
from driver.types import OSSConfig
from utils.proxy_manager import ProxyManager

class ConfigManager:
    CONFIG_FILE = "config.json"
    TIMEOUT = 30  # 超时时间（秒）
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        if not os.path.exists(self.CONFIG_FILE):
            self.save_config({})
        # 只加载配置，不初始化客户端
        self.config = self.load_config()
        self.oss_clients = {}
    
    def _init_client_with_timeout(self, client_class, config) -> tuple:
        """在超时限制内初始化客户端"""
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(client_class, config)
            try:
                # 获取当前代理状态
                proxy_manager = ProxyManager()
                proxy_settings = proxy_manager.get_proxy()
                self.logger.info(f"Initializing client with proxy settings: {proxy_settings}")
                
                client = future.result(timeout=self.TIMEOUT)
                return True, client
            except TimeoutError:
                self.logger.error(f"Client initialization timed out after {self.TIMEOUT} seconds")
                return False, None
            except Exception as e:
                self.logger.error(f"Failed to initialize client: {str(e)}")
                return False, None
    
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
        """保存配置"""
        try:
            with open(self.CONFIG_FILE, 'w') as f:
                json.dump(config, f, indent=4)
            self.config = config  # 更新内存中的配置
            return True
        except Exception as e:
            self.logger.error(f"Failed to save config: {e}")
            return False
    
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
            # 清除现有的客户端
            self.oss_clients.clear()
            
            # 重新加载配置
            self.config = self.load_config()
            
            # 重新初始化所有可用的客户端
            for name in self.get_available_clients():
                # 按需初始化客户端
                client = self.get_client(name)
                if client:
                    self.logger.info(f"Successfully reloaded {name} client")
            
            # 如果有主窗口引用，更新UI
            if hasattr(self, 'main_window'):
                self.main_window.update_oss_clients(self.oss_clients)
                
            self.logger.info("Successfully reloaded all clients")
            
        except Exception as e:
            self.logger.error(f"Failed to reload clients: {e}")
            raise
    
    def get_client(self, name: str) -> Optional[BaseOSSClient]:
        """获取或初始化客户端"""
        if name not in self.oss_clients:
            if name in self.config:
                # 确保代理设置已经加载
                proxy_manager = ProxyManager()
                if not hasattr(self, '_proxy_checked'):
                    self.logger.info(f"Current proxy settings: {proxy_manager.get_proxy()}")
                    self._proxy_checked = True
                
                client_config = self.config[name].copy()
                provider = client_config.get('provider')  # 从配置中获取provider
                if not provider:
                    self.logger.error(f"No provider specified for {name}")
                    return None
                
                success, client = self._init_client_with_timeout(
                    self._get_client_class(provider),  # 使用provider来获取客户端类
                    OSSConfig(**client_config)
                )
                if success:
                    self.oss_clients[name] = client
                    self.logger.info(f"{name} client loaded successfully")
                else:
                    return None
        return self.oss_clients.get(name)
    
    def _get_client_class(self, provider: str):
        """根据提供商获取客户端类"""
        if not provider:
            raise ValueError("No provider specified")
        
        provider = provider.lower()  # 转换为小写以确保匹配
        if provider == 'aliyun':
            return AliyunOSSClient
        elif provider == 'aws':
            return AWSS3Client
        elif provider == 'minio':
            return MinioClient
        raise ValueError(f"Unknown provider: {provider}")
    
    def get_available_clients(self) -> List[str]:
        """获取可用的客户端列表"""
        return list(self.config.keys())
    
    # 添加编辑功能
