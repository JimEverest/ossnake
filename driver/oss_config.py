from typing import Dict, Optional
import json
from dataclasses import dataclass

@dataclass
class ProxyConfig:
    http: Optional[str] = None
    https: Optional[str] = None

class OSSConfigManager:
    def __init__(self, config_file: str):
        self.config_file = config_file
        self.providers: Dict[str, OSSConfig] = {}
        self.load_config()
    
    def load_config(self) -> None:
        """从配置文件加载配置"""
        with open(self.config_file, 'r') as f:
            config_data = json.load(f)
            for provider, settings in config_data.items():
                self.providers[provider] = OSSConfig(**settings)
    
    def save_config(self) -> None:
        """保存配置到文件"""
        config_data = {name: vars(config) for name, config in self.providers.items()}
        with open(self.config_file, 'w') as f:
            json.dump(config_data, f, indent=2)
    
    def add_provider(self, name: str, config: OSSConfig) -> None:
        """添加新的OSS提供商配置"""
        self.providers[name] = config
        self.save_config()
    
    def remove_provider(self, name: str) -> None:
        """移除OSS提供商配置"""
        if name in self.providers:
            del self.providers[name]
            self.save_config() 