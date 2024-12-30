import json
import os
import logging
from typing import Dict, Any, Optional

class SettingsManager:
    """设置管理器"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.settings_file = "settings.json"
        self.default_settings = {
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
        self.settings = self.load_settings()
    
    def load_settings(self) -> Dict[str, Any]:
        """加载设置"""
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                # 合并默认设置，确保所有必要的键都存在
                return self._merge_settings(self.default_settings, settings)
            return self.default_settings.copy()
        except Exception as e:
            self.logger.error(f"Failed to load settings: {e}")
            return self.default_settings.copy()
    
    def save_settings(self, settings: Dict[str, Any]) -> bool:
        """保存设置"""
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=4, ensure_ascii=False)
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
        settings = self.load_settings()
        if settings.get("proxy", {}).get("enabled", False):
            # 只有在启用代理且有有效地址时才返回
            http_proxy = settings["proxy"].get("http", "").strip()
            https_proxy = settings["proxy"].get("https", "").strip()
            if http_proxy or https_proxy:
                return {
                    "http": http_proxy or None,
                    "https": https_proxy or None
                }
        return None 