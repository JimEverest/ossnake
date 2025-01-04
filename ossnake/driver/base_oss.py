from abc import ABC, abstractmethod
from typing import List, Optional, BinaryIO, Dict
import os
from .types import OSSConfig, ProgressCallback, MultipartUpload
import functools
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import logging
from ossnake.utils.proxy_manager import ProxyManager

def with_timeout(timeout_seconds=30):
    """超时装饰器"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(func, *args, **kwargs)
                try:
                    return future.result(timeout=timeout_seconds)
                except TimeoutError:
                    raise ConnectionError(f"Operation timed out after {timeout_seconds} seconds")
        return wrapper
    return decorator

class BaseOSSClient(ABC):
    """统一的OSS客户端基类"""
    
    TRANSFER_MANAGER_THRESHOLD = 5 * 1024 * 1024  # 5MB
    
    def __init__(self, config: OSSConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.connected = False
        
        # 获取代理设置并记录日志
        proxy_manager = ProxyManager()
        self.proxy_settings = proxy_manager.get_proxy()
        
        # 记录详细的代理信息
        self.logger.info(f"Initializing OSS client for endpoint: {config.endpoint}")
        self.logger.info(f"Using proxy settings: {self.proxy_settings}")
        
        # 记录环境变量状态
        env_proxies = {
            'HTTP_PROXY': os.environ.get('HTTP_PROXY'),
            'HTTPS_PROXY': os.environ.get('HTTPS_PROXY'),
            'http_proxy': os.environ.get('http_proxy'),
            'https_proxy': os.environ.get('https_proxy')
        }
        self.logger.info(f"Current proxy environment variables: {env_proxies}")
        
        # 初始化客户端
        self._init_client()
    
    @with_timeout(30)
    def _init_client_with_timeout(self):
        """带超时的客户端初始化"""
        self._init_client()
    
    @abstractmethod
    def _init_client(self) -> None:
        """初始化具体的客户端"""
        pass
    
    @abstractmethod
    def _upload_file(
        self,
        local_file: str,
        object_name: str,
        progress_callback: Optional[ProgressCallback] = None
    ) -> str:
        """实际的文件上传实现"""
        pass
    
    def upload_file(
        self,
        local_file: str,
        object_name: Optional[str] = None,
        progress_callback: Optional[ProgressCallback] = None,
        content_type: Optional[str] = None
    ) -> str:
        """上传文件
        Args:
            local_file: 本地文件路径
            object_name: 对象名称
            progress_callback: 进度回调接口
            content_type:  MIME类型 (新增)
        Returns:
            str: 文件访问URL
        """
        if os.path.getsize(local_file) > self.TRANSFER_MANAGER_THRESHOLD:
            from .transfer_manager import TransferManager
            manager = TransferManager()
            return manager.upload_file(self, local_file, object_name, progress_callback)
        return self._upload_file(local_file, object_name, progress_callback)
    
    @abstractmethod
    def upload_stream(self, 
                     stream: BinaryIO, 
                     object_name: str,
                     length: int = -1,
                     content_type: Optional[str] = None) -> str:
        """上传流数据并返回可访问的URL"""
        pass
    
    def download_file(self, remote_path: str, local_path: str, progress_callback=None):
        """下载文件"""
        raise NotImplementedError
    
    @abstractmethod
    def delete_file(self, object_name: str) -> None:
        """删除对象"""
        pass
    
    def list_objects(self, prefix: str = '', delimiter: str = '/') -> List[Dict]:
        """列出对象，支持分页加载所有对象
        Args:
            prefix: 前缀
            delimiter: 分隔符，用于模拟文件夹结构
        Returns:
            List[Dict]: 对象列表，每个对象包含 name, size, last_modified, type 等信息
        """
        try:
            all_objects = []
            folders = set()  # 用于去重文件夹
            
            # 获取所有对象
            continuation_token = None
            while True:
                result = self._list_objects_page(
                    prefix=prefix,
                    delimiter=delimiter,
                    continuation_token=continuation_token
                )
                
                # 处理文件夹
                for prefix in result.get('common_prefixes', []):
                    folder_name = prefix.rstrip('/')
                    if folder_name not in folders and folder_name != prefix:
                        folders.add(folder_name)
                        all_objects.append({
                            'name': folder_name,
                            'type': 'folder',
                            'size': 0,
                            'last_modified': None
                        })
                
                # 处理文件
                for obj in result.get('objects', []):
                    if obj['name'] != prefix:  # 排除当前目录
                        all_objects.append(obj)
                
                # 检查是否还有更多数据
                continuation_token = result.get('next_token')
                if not continuation_token:
                    break
            
            # 排序：文件夹在前，同类型按名称排序
            all_objects.sort(key=lambda x: (
                0 if x['type'] == 'folder' else 1,  # 文件夹优先
                x['name'].lower()  # 按名称排序
            ))
            
            return all_objects
            
        except Exception as e:
            self.logger.error(f"Failed to list objects: {str(e)}")
            raise
    
    @abstractmethod
    def get_presigned_url(self, object_name: str, expires: int = 3600) -> str:
        """获取预签名URL"""
        pass
    
    @abstractmethod
    def get_public_url(self, object_name: str) -> str:
        """获取公共访问URL"""
        pass
    
    @abstractmethod
    def create_folder(self, folder_name: str) -> None:
        """创建文件夹（通过创建空对象实现）"""
        pass
    
    @abstractmethod
    def move_object(self, source: str, destination: str) -> None:
        """移动/重命名对象"""
        pass
    
    @abstractmethod
    def list_buckets(self) -> List[Dict]:
        """列出所有可用的存储桶"""
        pass
    
    @abstractmethod
    def set_bucket_policy(self, policy: Dict) -> None:
        """设置存储桶策略"""
        pass 
    
    @abstractmethod
    def init_multipart_upload(self, object_name: str) -> MultipartUpload:
        """初始化分片上传"""
        pass
        
    @abstractmethod
    def upload_part(self, upload: MultipartUpload, part_number: int, data: bytes) -> str:
        """上传分片，返回ETag"""
        pass
        
    @abstractmethod
    def complete_multipart_upload(self, upload: MultipartUpload) -> str:
        """完成分片上传，返回文件URL"""
        pass
        
    @abstractmethod
    def abort_multipart_upload(self, upload: MultipartUpload) -> None:
        """取消分片上传"""
        pass 
    
    def _handle_auth_error(self, error):
        """统一处理认证错误"""
        error_msg = str(error).lower()
        if any(x in error_msg for x in [
            'access denied', 'invalid', 'credentials', 'forbidden', 
            'accessdenied', 'invalidaccesskeyid', 'signaturemismatch'
        ]):
            raise AuthenticationError("Invalid credentials or access denied")
    
    def _handle_network_error(self, error):
        """统一处理网络错误"""
        error_msg = str(error).lower()
        if any(x in error_msg for x in ['timeout', 'connection', 'network']):
            raise ConnectionError(f"Network error: {error_msg}")
    
    def _handle_sdk_error(self, error, operation: str = None):
        """统一处理SDK错误"""
        error_msg = str(error).lower()
        error_info = {
            'operation': operation,
            'original_error': error
        }

        # 认证错误
        if any(x in error_msg for x in ['access denied', 'forbidden', 'invalid credentials']):
            raise AuthenticationError(f"Authentication failed: {error_msg}", **error_info)
        
        # 存储桶错误
        if any(x in error_msg for x in ['no such bucket', 'bucket not found']):
            raise BucketNotFoundError(f"Bucket not found: {error_msg}", **error_info)
        
        # 对象错误
        if any(x in error_msg for x in ['no such key', 'object not found']):
            raise ObjectNotFoundError(f"Object not found: {error_msg}", **error_info)
        
        # 连接错误
        if any(x in error_msg for x in ['timeout', 'connection', 'network']):
            raise ConnectionError(f"Network error: {error_msg}", **error_info)
        
        # 其他错误
        raise UploadError(f"Operation failed: {error_msg}", **error_info)
    
    @abstractmethod
    def get_object(self, object_name: str) -> bytes:
        """获取对象内容
        Args:
            object_name: 对象名称
        Returns:
            bytes: 对象内容
        Raises:
            ObjectNotFoundError: 对象不存在
            OSSError: 其他错误
        """
        pass