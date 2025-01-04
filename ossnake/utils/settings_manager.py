import json
import os
import logging
import sys
from pathlib import Path
from typing import Dict, Any, Optional

class SettingsManager:
    """设置管理器"""
    
    # 将默认设置定义为类常量
    DEFAULT_SETTINGS = {
        "proxy": {
            "enabled": False,
            "http": "",
            "https": ""
        },
        "api": {
            "enabled": False,
            "port": 8000,
            "default_oss": ""
        },
        "upload": {
            "multipart_enabled": True,
            "chunk_size": 5,  # MB
            "workers": 4
        },
        "download": {
            "multipart_enabled": True,
            "chunk_size": 5,  # MB
            "workers": 4
        },
        "default": {
            "oss_source": "",
        },
        "list": {
            "page_size": 1000
        },
        "security": {
            "client_encryption": False,
            "encryption_method": "AES-256",
            "secure_transfer": True
        },
        "theme": {
            "mode": "system",
            "color": "blue"
        },
        "advanced": {
            "cache_size": 1024,  # MB
            "log_level": "INFO"
        }
    }
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # 获取程序所在目录
        if getattr(sys, 'frozen', False):
            self.app_dir = Path(sys._MEIPASS)
        else:
            self.app_dir = Path(os.path.dirname(os.path.dirname(__file__)))
        
        # 获取用户数据目录
        self.user_data_dir = Path(os.path.expanduser("~/.ossnake"))
        self.user_data_dir.mkdir(exist_ok=True)
        
        # 设置文件路径
        self.settings_path = self.user_data_dir / "settings.json"
        
        # 打印设置文件路径
        self.logger.info(f"Settings file path: {self.settings_path}")
        
        # 加载或创建设置
        self.settings = self.load_settings()
    
    def _create_default_settings(self) -> None:
        """创建默认设置文件"""
        try:
            with open(self.settings_path, 'w', encoding='utf-8') as f:
                json.dump(self.DEFAULT_SETTINGS, f, indent=4, ensure_ascii=False)
            self.logger.info(f"Created default settings at: {self.settings_path}")
        except Exception as e:
            self.logger.error(f"Failed to create default settings: {e}")
            raise  # 重新抛出异常，因为这是关键操作
    
    def load_settings(self) -> Dict[str, Any]:
        """加载设置，如果文件不存在则创建默认设置"""
        try:
            if not self.settings_path.exists():
                self._create_default_settings()
                return self.DEFAULT_SETTINGS.copy()
            
            with open(self.settings_path, 'r', encoding='utf-8') as f:
                settings = json.load(f)
            # 合并默认设置，确保所有必要的键都存在
            return self._merge_settings(self.DEFAULT_SETTINGS, settings)
            
        except Exception as e:
            self.logger.error(f"Failed to load settings: {e}")
            return self.DEFAULT_SETTINGS.copy()
    
    def save_settings(self, settings: Dict[str, Any]) -> bool:
        """保存设置"""
        try:
            # 先验证设置结构
            merged_settings = self._merge_settings(self.DEFAULT_SETTINGS, settings)
            
            with open(self.settings_path, 'w', encoding='utf-8') as f:
                json.dump(merged_settings, f, indent=4, ensure_ascii=False)
            
            self.settings = merged_settings
            self.logger.info("Settings saved successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to save settings: {e}")
            return False
    
    def _merge_settings(self, default: Dict, current: Dict) -> Dict:
        """合并设置，确保所有默认键都存在"""
        result = default.copy()
        for key, value in current.items():
            if key in result:
                if isinstance(value, dict) and isinstance(result[key], dict):
                    result[key] = self._merge_settings(result[key], value)
                else:
                    result[key] = value
        return result 
    
    def get_proxy_settings(self) -> Optional[Dict[str, str]]:
        """获取代理设置"""
        try:
            # 直接使用已加载的设置，而不是重新加载
            proxy_settings = self.settings.get("proxy", {})
            if proxy_settings.get("enabled", False):
                http_proxy = proxy_settings.get("http", "").strip()
                https_proxy = proxy_settings.get("https", "").strip()
                if http_proxy or https_proxy:
                    return {
                        "http": http_proxy or None,
                        "https": https_proxy or None
                    }
            return None
        except Exception as e:
            self.logger.error(f"Failed to get proxy settings: {e}")
            return None 