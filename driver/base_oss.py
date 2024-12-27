from abc import ABC, abstractmethod
from typing import List, Optional, BinaryIO, Dict
import os
from .types import OSSConfig, ProgressCallback, MultipartUpload

class BaseOSSClient(ABC):
    """统一的OSS客户端基类"""
    
    TRANSFER_MANAGER_THRESHOLD = 5 * 1024 * 1024  # 5MB
    
    def __init__(self, config: OSSConfig):
        self.config = config
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
    
    @abstractmethod
    def download_file(self, object_name: str, local_file: str, progress_callback: Optional[ProgressCallback] = None) -> None:
        """下载文件到本地"""
        pass
    
    @abstractmethod
    def delete_file(self, object_name: str) -> None:
        """删除对象"""
        pass
    
    @abstractmethod
    def list_objects(self, prefix: str = '', recursive: bool = True) -> List[Dict]:
        """列出对象，返回包含详细信息的字典列表"""
        pass
    
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
        """统一的SDK错误处理"""
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