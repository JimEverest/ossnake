import os
import logging
from typing import Optional, Dict
from urllib.parse import urlparse, urlunparse, parse_qs

class ProxyManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self.logger = logging.getLogger(__name__)
            self._proxy_settings = None
            self._initialized = True
    
    def set_proxy(self, proxy_settings: Optional[Dict[str, str]]) -> None:
        """设置代理"""
        self.logger.info(f"Setting proxy with settings: {proxy_settings}")
        
        # 记录当前环境变量状态
        current_env = {
            'HTTP_PROXY': os.environ.get('HTTP_PROXY'),
            'HTTPS_PROXY': os.environ.get('HTTPS_PROXY'),
            'http_proxy': os.environ.get('http_proxy'),
            'https_proxy': os.environ.get('https_proxy')
        }
        self.logger.info(f"Current proxy environment variables: {current_env}")
        
        # 清除现有环境变量和设置
        self._clear_proxy()
        
        # 只有当代理设置存在且有效时才设置
        if proxy_settings and any(value for value in proxy_settings.values() if value):
            self._proxy_settings = proxy_settings
            if proxy_settings.get("http"):
                os.environ["HTTP_PROXY"] = proxy_settings["http"]
                os.environ["http_proxy"] = proxy_settings["http"]
                self.logger.info(f"Set HTTP proxy: {proxy_settings['http']}")
            if proxy_settings.get("https"):
                os.environ["HTTPS_PROXY"] = proxy_settings["https"]
                os.environ["https_proxy"] = proxy_settings["https"]
                self.logger.info(f"Set HTTPS proxy: {proxy_settings['https']}")
            
            # 记录设置后的环境变量状态
            new_env = {
                'HTTP_PROXY': os.environ.get('HTTP_PROXY'),
                'HTTPS_PROXY': os.environ.get('HTTPS_PROXY'),
                'http_proxy': os.environ.get('http_proxy'),
                'https_proxy': os.environ.get('https_proxy')
            }
            self.logger.info(f"Updated proxy environment variables: {new_env}")
        else:
            self.logger.info("Proxy disabled, using direct connection")
    
    def _clear_proxy(self):
        """清除所有代理设置"""
        if self._proxy_settings:
            self.logger.info(f"Clearing previous proxy settings: {self._proxy_settings}")
        self._proxy_settings = None
        # 清除所有可能的代理环境变量
        for var in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]:
            if var in os.environ:
                self.logger.info(f"Removing environment variable: {var}")
                os.environ.pop(var)
    
    def get_proxy(self) -> Optional[Dict[str, str]]:
        """获取当前代理设置"""
        return self._proxy_settings if self._proxy_settings and any(self._proxy_settings.values()) else None
    
    @staticmethod
    def format_proxy_url(url: str) -> str:
        """格式化代理URL，确保格式正确
        Args:
            url: 代理URL，可能包含用户名密码
        Returns:
            str: 格式化后的URL
        """
        if not url:
            return ""
            
        # 如果URL不包含协议，添加http://
        if not url.startswith(("http://", "https://")):
            url = f"http://{url}"
            
        try:
            parsed = urlparse(url)
            # 确保用户名密码正确编码
            if "@" in parsed.netloc:
                auth, host = parsed.netloc.split("@", 1)
                if ":" in auth:
                    username, password = auth.split(":", 1)
                    # 重新构建URL，确保正确编码
                    netloc = f"{username}:{password}@{host}"
                    parsed = parsed._replace(netloc=netloc)
            
            return urlunparse(parsed)
        except Exception as e:
            logging.error(f"Failed to format proxy URL: {e}")
            return url 