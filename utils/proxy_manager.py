import os
import logging
from typing import Optional, Dict
from urllib.parse import urlparse, urlunparse, parse_qs

class ProxyManager:
    """代理管理器"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._proxy_settings = None
    
    def set_proxy(self, proxy_settings: Optional[Dict[str, str]]) -> None:
        """设置代理
        Args:
            proxy_settings: 代理设置字典，格式为 {"http": "http://...", "https": "http://..."}
        """
        self._proxy_settings = proxy_settings
        if proxy_settings:
            # 设置环境变量
            if proxy_settings.get("http"):
                os.environ["HTTP_PROXY"] = proxy_settings["http"]
            if proxy_settings.get("https"):
                os.environ["HTTPS_PROXY"] = proxy_settings["https"]
            self.logger.info("Proxy enabled")
        else:
            # 清除环境变量
            os.environ.pop("HTTP_PROXY", None)
            os.environ.pop("HTTPS_PROXY", None)
            self.logger.info("Proxy disabled")
    
    def get_proxy(self) -> Optional[Dict[str, str]]:
        """获取当前代理设置"""
        return self._proxy_settings
    
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