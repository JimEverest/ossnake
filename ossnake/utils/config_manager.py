# utils/config_manager.py
# 实现一个配置管理器，用于管理多个OSS源的配置，包括添加、编辑和删除。
import json
import os
import logging
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Dict, Optional, List
from ossnake.driver.base_oss import BaseOSSClient
from ossnake.driver.aws_s3 import AWSS3Client
from ossnake.driver.oss_ali import AliyunOSSClient
from ossnake.driver.minio_client import MinioClient
from ossnake.driver.types import OSSConfig
from ossnake.utils.proxy_manager import ProxyManager

class ConfigManager:
    CONFIG_FILE = "config.json"
    TIMEOUT = 30  # 超时时间（秒）
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # 获取程序所在目录
        if getattr(sys, 'frozen', False):
            # PyInstaller 打包后的路径
            self.app_dir = Path(sys._MEIPASS)
        else:
            # 开发环境路径
            self.app_dir = Path(os.path.dirname(os.path.dirname(__file__)))
        
        # 获取用户数据目录
        self.user_data_dir = Path(os.path.expanduser("~/.ossnake"))
        self.user_data_dir.mkdir(exist_ok=True)
        
        # 配置文件路径
        self.config_path = self.user_data_dir / "config.json"
        self.settings_path = self.user_data_dir / "settings.json"
        
        # 打印配置文件路径
        self.logger.info(f"Application directory: {self.app_dir}")
        self.logger.info(f"User data directory: {self.user_data_dir}")
        self.logger.info(f"Config file path: {self.config_path}")
        self.logger.info(f"Settings file path: {self.settings_path}")
        
        # 如果配置文件不存在，从包中复制默认配置
        if not self.config_path.exists():
            self._copy_default_config()
        if not self.settings_path.exists():
            self._copy_default_settings()
        
        # 加载配置
        self.config = self.load_config()
        self.oss_clients = {}
    
    def _copy_default_config(self):
        """从包中复制默认配置文件"""
        try:
            default_config = self.app_dir / "config.json"
            self.logger.info(f"Looking for default config at: {default_config}")
            if default_config.exists():
                import shutil
                shutil.copy2(default_config, self.config_path)
                self.logger.info(f"Copied default config to: {self.config_path}")
            else:
                self.logger.warning(f"Default config not found at {default_config}, creating new one")
                self.create_default_config()
        except Exception as e:
            self.logger.error(f"Failed to copy default config: {e}")
            self.create_default_config()

    def _copy_default_settings(self):
        """从包中复制默认设置文件"""
        try:
            default_settings = self.app_dir / "settings.json"
            if default_settings.exists():
                import shutil
                shutil.copy2(default_settings, self.settings_path)
                self.logger.info(f"Copied default settings to: {self.settings_path}")
            else:
                self.create_default_settings()
        except Exception as e:
            self.logger.error(f"Failed to copy default settings: {e}")
            self.create_default_settings()
    
    def create_default_config(self):
        """创建默认配置文件"""
        default_config = {
            "oss_clients": {
                "example_aliyun": {
                    "provider": "aliyun",
                    "access_key": "your_access_key",
                    "secret_key": "your_secret_key",
                    "endpoint": "oss-cn-hangzhou.aliyuncs.com",
                    "bucket_name": "your_bucket"
                }
            }
        }
        
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=4, ensure_ascii=False)
            self.logger.info(f"Created default config file at: {self.config_path}")
            self.logger.info(f"Default config content: {json.dumps(default_config, indent=2)}")
        except Exception as e:
            self.logger.error(f"Failed to create default config: {str(e)}")
    
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
        """加载配置"""
        try:
            self.logger.info(f"Attempting to load config from: {self.config_path}")
            
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                self.logger.info(f"Loaded raw config content: {json.dumps(config, indent=2)}")
                
                # 如果配置不是期望的结构，进行转换
                if not config.get("oss_clients") and any(k in config for k in ["aws", "aliyun", "minio"]):
                    self.logger.info("Converting old config format to new format")
                    new_config = {
                        "oss_clients": {
                            k: v for k, v in config.items() 
                            if k in ["aws", "aliyun", "minio"]
                        }
                    }
                    
                    # 保存新格式
                    self.save_config(new_config)
                    config = new_config
                
                self.logger.info(f"Final config structure: {json.dumps(config, indent=2)}")
                return config
                
        except Exception as e:
            self.logger.error(f"Error loading config: {str(e)}")
            return {"oss_clients": {}}
    
    def save_config(self, config):
        """保存配置"""
        try:
            # 确保配置有正确的结构
            if not isinstance(config, dict):
                raise ValueError("Config must be a dictionary")
            
            # 如果有客户端配置但不在 oss_clients 中，自动修正
            if any(k in config for k in ["aws", "aliyun", "minio"]) and "oss_clients" not in config:
                self.logger.warning("Found client config at root level, moving to oss_clients")
                new_config = {
                    "oss_clients": {
                        k: v for k, v in config.items() 
                        if k not in ["oss_clients"]  # 避免重复
                    }
                }
                config = new_config

            # 保存配置
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
            self.config = config
            self.logger.info(f"Config saved to: {self.config_path}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to save config: {e}")
            return False
    
    def add_client(self, name: str, config: dict):
        """添加OSS客户端配置"""
        try:
            config_data = self.load_config()
            # 确保 oss_clients 存在
            if "oss_clients" not in config_data:
                config_data["oss_clients"] = {}
            
            # 添加到 oss_clients 中
            config_data["oss_clients"][name] = config
            
            # 保存配置
            self.save_config(config_data)
            self.logger.info(f"Added OSS client: {name}")
            
        except Exception as e:
            self.logger.error(f"Failed to add client {name}: {e}")
            raise
    
    def remove_client(self, name: str):
        """移除OSS客户端配置"""
        try:
            config_data = self.load_config()
            # 从 oss_clients 中删除
            if name in config_data.get("oss_clients", {}):
                del config_data["oss_clients"][name]
                # 如果客户端已初始化，也要移除
                if name in self.oss_clients:
                    del self.oss_clients[name]
                
                # 保存配置
                self.save_config(config_data)
                self.logger.info(f"Removed OSS client: {name}")
                
        except Exception as e:
            self.logger.error(f"Failed to remove client {name}: {e}")
            raise
    
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
            # 从 oss_clients 字典中获取配置
            oss_clients = self.config.get("oss_clients", {})
            if name in oss_clients:
                # 确保代理设置已经加载
                proxy_manager = ProxyManager()
                if not hasattr(self, '_proxy_checked'):
                    self.logger.info(f"Current proxy settings: {proxy_manager.get_proxy()}")
                    self._proxy_checked = True
                
                client_config = oss_clients[name].copy()
                provider = client_config.get('provider')
                
                if not provider:
                    self.logger.error(f"No provider specified for {name}")
                    return None
                
                self.logger.info(f"Initializing client for {name} with config: {client_config}")
                
                success, client = self._init_client_with_timeout(
                    self._get_client_class(provider),
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
        oss_clients = self.config.get("oss_clients", {})
        client_list = list(oss_clients.keys())
        self.logger.info(f"Available clients: {client_list}")
        return client_list
    
    # 添加编辑功能
