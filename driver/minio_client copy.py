from typing import List, Optional, BinaryIO, Dict, Union, IO
from minio import Minio
from minio.error import S3Error
import os
from datetime import datetime, timedelta
from urllib.parse import urlparse
from io import BytesIO
import time
import tempfile
import urllib3
import logging

from .types import OSSConfig, ProgressCallback, MultipartUpload
from .base_oss import BaseOSSClient
from .exceptions import (
    OSSError, ConnectionError, AuthenticationError, 
    ObjectNotFoundError, BucketNotFoundError, 
    UploadError, DownloadError, TransferError, BucketError, GetUrlError, DeleteError
)

# 配置日志
logger = logging.getLogger(__name__)

class MinioClient(BaseOSSClient):
    """
    MinIO客户端实现
    
    实现了BaseOSSClient定义的所有抽象方法，提供完整的MinIO操作接口。
    支持标准S3协议的存储服务。
    """

    def __init__(self, config: OSSConfig):
        """初始化MinIO客户端"""
        self.config = config
        
        try:
            # 配置代理
            if hasattr(config, 'proxy') and config.proxy:
                proxy_url = config.proxy
                logger.info(f"Initializing MinIO client with proxy: {proxy_url}")
                http_client = urllib3.ProxyManager(
                    proxy_url,
                    timeout=urllib3.Timeout(connect=5.0, read=15.0),
                    maxsize=8,
                    retries=urllib3.Retry(
                        total=2,
                        backoff_factor=0.5,
                        status_forcelist=[500, 502, 503, 504]
                    )
                )
            else:
                http_client = urllib3.PoolManager(
                    timeout=urllib3.Timeout(connect=5.0, read=15.0),
                    maxsize=8,
                    retries=urllib3.Retry(
                        total=2,
                        backoff_factor=0.5,
                        status_forcelist=[500, 502, 503, 504]
                    )
                )

            # 创建MinIO客户端
            self.client = Minio(
                endpoint=config.endpoint,
                access_key=config.access_key,
                secret_key=config.secret_key,
                secure=config.secure,
                http_client=http_client
            )
            
            # 验证连接和代理
            try:
                self.client.list_buckets()
                logger.info("Successfully connected to MinIO server")
            except Exception as e:
                raise ConnectionError(f"Failed to connect to MinIO server: {str(e)}")
            
        except Exception as e:
            raise ConnectionError(f"Failed to initialize MinIO client: {str(e)}")

    def _init_client(self) -> None:
        """初始化 MinIO 客户端"""
        try:
            # 添加超时配置
            self.client = Minio(
                self.config.endpoint,
                access_key=self.config.access_key,
                secret_key=self.config.secret_key,
                secure=self.config.secure,
                # 添加超时设置
                http_client=urllib3.PoolManager(
                    timeout=urllib3.Timeout(connect=5.0, read=10.0),
                    retries=urllib3.Retry(
                        total=3,
                        backoff_factor=0.2,
                        status_forcelist=[500, 502, 503, 504]
                    )
                )
            )
        except Exception as e:
            raise ConnectionError(f"Failed to initialize MinIO client: {str(e)}")

    def _ensure_bucket(self):
        """
        Ensure the bucket exists, create if not.
        """
        try:
            if not self.client.bucket_exists(self.config.bucket_name):
                self.client.make_bucket(self.config.bucket_name)
        except S3Error as e:
            raise BucketError(f"Failed to ensure bucket exists: {str(e)}")

    def _upload_file(
        self,
        local_file: str,
        object_name: str,
        progress_callback: Optional[ProgressCallback] = None
    ) -> str:
        """实际的文件上传实现"""
        try:
            if not os.path.exists(local_file):
                raise FileNotFoundError(f"Local file not found: {local_file}")
                
            if object_name is None:
                object_name = os.path.basename(local_file)
            
            # 创建进度回调包装器
            if progress_callback:
                total_size = os.path.getsize(local_file)
                start_time = datetime.now()
                
                class ProgressWrapper:
                    def __init__(self):
                        self.bytes_transferred = 0
                        
                    def __call__(self, size):
                        try:
                            self.bytes_transferred += size
                            elapsed = (datetime.now() - start_time).total_seconds()
                            speed = self.bytes_transferred / elapsed if elapsed > 0 else 0
                            if callable(progress_callback):
                                progress_callback(self.bytes_transferred, total_size)
                        
                        except Exception as e:
                            # 不使用 self.logger，直接打印错误
                            print(f"Progress callback failed: {e}")
                        
                    def update(self, size):
                        """MinIO需要这个方法"""
                        self.__call__(size)
                        
                    def set_meta(self, **kwargs):
                        """MinIO需要这个方法"""
                        pass
                
                progress_wrapper = ProgressWrapper()
            else:
                progress_wrapper = None
            
            # 上传文件
            result = self.client.fput_object(
                self.config.bucket_name,
                object_name,
                local_file,
                progress=progress_wrapper,
                content_type=self._get_content_type(local_file)
            )
            return self.get_public_url(object_name)
            
        except S3Error as e:
            error_msg = str(e)
            if 'NoSuchBucket' in error_msg:
                raise BucketNotFoundError(f"Bucket {self.config.bucket_name} not found")
            elif 'NoSuchKey' in error_msg:
                raise ObjectNotFoundError(f"Object {object_name} not found")
            elif 'AccessDenied' in error_msg:
                raise AuthenticationError("Access denied - please check your credentials")
            elif 'RequestTimeout' in error_msg:
                raise ConnectionError("Connection timed out - please check your network")
            else:
                raise UploadError(f"Upload failed: {error_msg}")

    def upload_stream(
        self,
        stream: BinaryIO,
        object_name: str,
        length: int = -1,
        content_type: Optional[str] = None
    ) -> str:
        """从流中上传数据到MinIO"""
        try:
            self.client.put_object(
                self.config.bucket_name,
                object_name,
                stream,
                length,
                content_type=content_type or 'application/octet-stream'
            )
            return self.get_public_url(object_name)
        except S3Error as e:
            if 'NoSuchBucket' in str(e):
                raise BucketNotFoundError(str(e))
            elif 'AccessDenied' in str(e):
                raise AuthenticationError(str(e))
            else:
                raise UploadError(str(e))

    def download_file(self, object_name: str, local_file: str, progress_callback: Optional[ProgressCallback] = None) -> None:
        """从MinIO下载文件到本地"""
        try:
            # 确保目标目录存在
            os.makedirs(os.path.dirname(os.path.abspath(local_file)), exist_ok=True)
            
            if progress_callback:
                object_info = self.client.stat_object(self.config.bucket_name, object_name)
                total_size = object_info.size
                start_time = datetime.now()
                bytes_transferred = 0

                with open(local_file, 'wb') as f:
                    def callback(data):
                        nonlocal bytes_transferred
                        bytes_transferred += len(data)
                        elapsed = (datetime.now() - start_time).total_seconds()
                        speed = bytes_transferred / elapsed if elapsed > 0 else 0
                        progress_callback.on_progress(
                            bytes_transferred,
                            total_size,
                            start_time,
                            speed
                        )
                        return data

                    self.client.fget_object(
                        self.config.bucket_name,
                        object_name,
                        f,
                        progress=callback
                    )
            else:
                self.client.fget_object(
                    self.config.bucket_name,
                    object_name,
                    local_file
                )
            
        except S3Error as e:
            if 'NoSuchKey' in str(e):
                raise ObjectNotFoundError(str(e))
            elif 'NoSuchBucket' in str(e):
                raise BucketNotFoundError(str(e))
            elif 'AccessDenied' in str(e):
                raise AuthenticationError(str(e))
            else:
                raise DownloadError(str(e))

    def delete_file(self, object_name: str) -> None:
        """删除MinIO对象"""
        try:
            self.client.remove_object(self.config.bucket_name, object_name)
        except S3Error as e:
            if 'NoSuchBucket' in str(e):
                raise BucketNotFoundError(str(e))
            elif 'NoSuchKey' in str(e):
                raise ObjectNotFoundError(str(e))
            elif 'AccessDenied' in str(e):
                raise AuthenticationError(str(e))
            else:
                raise UploadError(str(e))

    def list_objects(self, prefix: str = '', recursive: bool = True) -> List[Dict]:
        """列出MinIO对象"""
        try:
            objects = []
            items = self.client.list_objects(
                self.config.bucket_name,
                prefix=prefix,
                recursive=recursive
            )
            
            for item in items:
                if item.is_dir:
                    objects.append({
                        'name': item.object_name,
                        'type': 'folder',
                        'size': 0,
                        'last_modified': None
                    })
                else:
                    objects.append({
                        'name': item.object_name,
                        'type': 'file',
                        'size': item.size,
                        'last_modified': item.last_modified,
                        'etag': item.etag.strip('"')
                    })
                    
            return objects
            
        except S3Error as e:
            if 'NoSuchBucket' in str(e):
                raise BucketNotFoundError(str(e))
            elif 'AccessDenied' in str(e):
                raise AuthenticationError(str(e))
            else:
                raise OSSError(f"Failed to list objects: {str(e)}")

    def get_presigned_url(self, object_name: str, expires: int = 3600) -> str:
        """获取预签名URL"""
        try:
            return self.client.get_presigned_url(
                'GET',
                self.config.bucket_name,
                object_name,
                expires=timedelta(seconds=expires)
            )
        except S3Error as e:
            if 'NoSuchBucket' in str(e):
                raise BucketNotFoundError(str(e))
            elif 'NoSuchKey' in str(e):
                raise ObjectNotFoundError(str(e))
            elif 'AccessDenied' in str(e):
                raise AuthenticationError(str(e))
            else:
                raise OSSError(f"Failed to generate presigned URL: {str(e)}")

    def get_public_url(self, object_name: str) -> str:
        """获取公共访问URL"""
        scheme = 'https' if self.config.secure else 'http'
        return f"{scheme}://{self.config.endpoint}/{self.config.bucket_name}/{object_name}"

    def create_folder(self, folder_name: str) -> None:
        """创建文件夹"""
        if not folder_name.endswith('/'):
            folder_name += '/'
        try:
            self.client.put_object(
                self.config.bucket_name,
                folder_name,
                io.BytesIO(b''),
                0
            )
        except S3Error as e:
            if 'NoSuchBucket' in str(e):
                raise BucketNotFoundError(str(e))
            elif 'AccessDenied' in str(e):
                raise AuthenticationError(str(e))
            else:
                raise OSSError(f"Failed to create folder: {str(e)}")

    def move_object(self, source: str, destination: str) -> None:
        """移动/重命名对象"""
        try:
            # MinIO需先复制删除
            self.client.copy_object(
                self.config.bucket_name,
                destination,
                f"{self.config.bucket_name}/{source}"
            )
            self.client.remove_object(self.config.bucket_name, source)
        except S3Error as e:
            if 'NoSuchBucket' in str(e):
                raise BucketNotFoundError(str(e))
            elif 'NoSuchKey' in str(e):
                raise ObjectNotFoundError(str(e))
            elif 'AccessDenied' in str(e):
                raise AuthenticationError(str(e))
            else:
                raise OSSError(f"Failed to move object: {str(e)}")

    def list_buckets(self) -> List[Dict]:
        """列出所有可用的存储桶"""
        try:
            return [{
                'name': bucket.name,
                'creation_date': bucket.creation_date
            } for bucket in self.client.list_buckets()]
        except S3Error as e:
            error_msg = str(e).lower()
            if 'access denied' in error_msg or 'invalid' in error_msg or 'credentials' in error_msg:
                raise AuthenticationError("Invalid credentials or access denied")
            elif 'no such bucket' in error_msg:
                raise BucketNotFoundError(f"Bucket not found")
            elif 'timeout' in error_msg or 'connection' in error_msg:
                raise ConnectionError("Network error - please check your connection")
            else:
                raise OSSError(f"Failed to list buckets: {error_msg}")

    def set_bucket_policy(self, policy: Dict) -> None:
        """设置存储桶策略"""
        try:
            self.client.set_bucket_policy(
                self.config.bucket_name,
                json.dumps(policy)
            )
        except S3Error as e:
            if 'NoSuchBucket' in str(e):
                raise BucketNotFoundError(str(e))
            elif 'AccessDenied' in str(e):
                raise AuthenticationError(str(e))
            else:
                raise OSSError(f"Failed to set bucket policy: {str(e)}")

    def _get_content_type(self, filename: str) -> str:
        """根据文件扩展名获取内容类型"""
        import mimetypes
        content_type, _ = mimetypes.guess_type(filename)
        return content_type or 'application/octet-stream' 

    def upload_file(
        self,
        local_file: str,
        object_name: Optional[str] = None,
        progress_callback: Optional[ProgressCallback] = None,
        content_type: Optional[str] = None
    ) -> str:
        """上传文件到MinIO并返回可访问的URL"""
        return self._upload_file(local_file, object_name, progress_callback)

    def init_multipart_upload(self, object_name: str) -> MultipartUpload:
        """初始化分片上传"""
        try:
            # MinIO 不需要显式初始化分片上传
            return MultipartUpload(
                upload_id=str(int(time.time())),  # 使用时间戳作为上传ID
                object_name=object_name,
                bucket_name=self.config.bucket_name,  # 添加bucket_name
                total_parts=0
            )
        except S3Error as e:
            raise OSSError(f"Failed to init multipart upload: {str(e)}")

    def upload_part(self, upload: MultipartUpload, part_number: int, data: BinaryIO) -> str:
        """上传分片"""
        try:
            # 计算分片大小
            data.seek(0, os.SEEK_END)
            part_size = data.tell()
            data.seek(0)

            result = self.client.put_object(
                bucket_name=upload.bucket_name,
                object_name=f"{upload.object_name}.part{part_number}",
                data=data,
                length=part_size
            )
            
            return result.etag
            
        except S3Error as e:
            raise OSSError(f"Failed to upload part: {str(e)}")

    def complete_multipart_upload(self, upload: MultipartUpload) -> str:
        """完成分片上传，返回文件URL"""
        try:
            # 创建一个临时文件来合并分片
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                # 下载并合并所有分片
                for part_number, etag in sorted(upload.parts):
                    part_name = f"{upload.object_name}.part{part_number}"
                    # 下载分片到临时文件
                    self.client.fget_object(
                        self.config.bucket_name,
                        part_name,
                        temp_file.name + f".part{part_number}"
                    )
                    # 合并分片
                    with open(temp_file.name + f".part{part_number}", 'rb') as part_file:
                        temp_file.write(part_file.read())
                    # 删除分片文
                    os.remove(temp_file.name + f".part{part_number}")
                    # 删除OSS上的分片
                    self.client.remove_object(self.config.bucket_name, part_name)
                
                # 上传完文件
                temp_file.flush()
                self.client.fput_object(
                    self.config.bucket_name,
                    upload.object_name,
                    temp_file.name
                )
            
            # 清理临时文件
            os.unlink(temp_file.name)
            
            return self.get_public_url(upload.object_name)
            
        except Exception as e:
            error_msg = str(e)
            if isinstance(e, S3Error):
                raise e
            else:
                raise S3Error(
                    message=error_msg,
                    resource=upload.object_name,
                    request_id=str(int(time.time())),  # 使用时间戳作为请求ID
                    host_id=self.config.endpoint,
                    response={'error': error_msg}
                )

    def abort_multipart_upload(self, upload: MultipartUpload) -> None:
        """取消分片上传"""
        try:
            # 删除所有已上传的分片
            for part_number, _ in upload.parts:
                part_name = f"{upload.object_name}.part{part_number}"
                try:
                    self.client.remove_object(self.config.bucket_name, part_name)
                except:
                    pass  # 忽略删除失败的分片
        except S3Error as e:
            raise S3Error(f"Failed to abort multipart upload: {str(e)}")

    def get_file_url(self, remote_path: str) -> str:
        """
        Get the URL of a file on MinIO.
        """
        try:
            return self.client.get_presigned_url(
                "GET",
                self.config.bucket_name,
                remote_path,
            )
        except S3Error as e:
            raise GetUrlError(f"Failed to get file URL: {str(e)}")

    def delete_file(self, remote_path: str) -> None:
        """
        Delete a file from MinIO.
        """
        try:
            self.client.remove_object(
                self.config.bucket_name,
                remote_path,
            )
        except S3Error as e:
            raise DeleteError(f"Failed to delete file: {str(e)}")