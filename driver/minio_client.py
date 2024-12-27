from typing import List, Optional, BinaryIO, Dict, Union, IO
from minio import Minio
import minio
from minio.error import S3Error
import os
from datetime import datetime, timedelta
from urllib.parse import urlparse
from io import BytesIO
import time
import tempfile
import urllib3
import logging
import shutil
import traceback

from .types import OSSConfig, ProgressCallback, MultipartUpload
from .base_oss import BaseOSSClient
from .exceptions import (
    OSSError, ConnectionError, AuthenticationError, 
    ObjectNotFoundError, BucketNotFoundError, 
    UploadError, DownloadError, TransferError, BucketError, GetUrlError, DeleteError
)

# 配置日志
logger = logging.getLogger(__name__)

class Part:
    """表示分片的简单类"""
    def __init__(self, part_number: int, etag: str):
        self.part_number = part_number
        self.etag = etag

class MinioClient(BaseOSSClient):
    """
    MinIO客户端实现
    
    实现了BaseOSSClient定义的所有抽象方法，提供完整的MinIO操作接口。
    支持标准S3协议的存储服务。
    """

    def __init__(self, config: OSSConfig):
        """初始化MinIO客户端"""
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        try:
            # 配置代理
            if hasattr(config, 'proxy') and config.proxy:
                proxy_url = config.proxy
                logger.info(f"Initializing MinIO client with proxy: {proxy_url}")
                http_client = urllib3.ProxyManager(
                    proxy_url,
                    timeout=urllib3.Timeout(connect=5.0, read=60.0),
                    maxsize=8,
                    retries=urllib3.Retry(
                        total=2,
                        backoff_factor=0.5,
                        status_forcelist=[500, 502, 503, 504]
                    )
                )
            else:
                http_client = urllib3.PoolManager(
                    timeout=urllib3.Timeout(connect=5.0, read=900.0),
                    maxsize=8,
                    retries=urllib3.Retry(
                        total=3,
                        backoff_factor=0.2,
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
                        """MinIO需这个方法"""
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
        """删除文件
        Args:
            object_name: 对象名称
        """
        try:
            # Check if the object exists before attempting to delete
            if not self.object_exists(object_name):
                raise ObjectNotFoundError(f"Object not found: {object_name}")

            self.client.remove_object(
                bucket_name=self.config.bucket_name,
                object_name=object_name
            )
        except S3Error as e:
            # If the error is not related to object existence, raise it
            if 'NoSuchKey' not in str(e):
                raise OSSError(f"Failed to delete file: {str(e)}")

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

    def get_presigned_url(self, object_name: str, expires: timedelta = timedelta(days=7)) -> str:
        """生成预签名URL"""
        try:
            url = self.client.presigned_get_object(
                self.config.bucket_name,
                object_name,
                expires=expires
            )
            return url
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
        """根据文件扩展名获内容类型"""
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
            # 使用 MinIO 的原生分片上传
            result = self.client._create_multipart_upload(
                self.config.bucket_name,
                object_name,
                {}  # headers
            )
            return MultipartUpload(
                object_name=object_name,
                upload_id=result
            )
        except S3Error as e:
            raise S3Error(f"Failed to init multipart upload: {str(e)}")

    def upload_part(self, upload: MultipartUpload, part_number: int, data: Union[bytes, IO], callback=None) -> str:
        """上传分片，返回ETag"""
        try:
            self.logger.debug(f"Starting upload_part: part_number={part_number}")
            
            # 准备数据
            if isinstance(data, bytes):
                data_len = len(data)
                data_to_upload = data
            else:
                data_bytes = data.read()
                data_len = len(data_bytes)
                data_to_upload = data_bytes
            
            # 创建一个���单的进度跟踪器
            uploaded = 0
            def progress_callback(chunk_size):
                nonlocal uploaded
                uploaded += chunk_size
                if callback:
                    callback(uploaded)
            
            # 使用 MinIO 的原生分片上传
            result = self.client._upload_part(
                bucket_name=self.config.bucket_name,
                object_name=upload.object_name,
                upload_id=upload.upload_id,
                part_number=part_number,
                data=data_to_upload,
                headers={"Content-Length": str(data_len)}
            )
            
            # 上传完成后，确保回调收到完整大小
            if callback:
                callback(data_len)
            
            return result

        except Exception as e:
            self.logger.error(f"Failed to upload part: {str(e)}")
            self.logger.error(f"Exception type: {type(e)}")
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            raise

    def complete_multipart_upload(self, upload: MultipartUpload) -> str:
        """完成分片上传，返回文件URL"""
        try:
            self.logger.info(f"\n{'-'*20} Complete Multipart Upload Details {'-'*20}")
            self.logger.info(f"Object: {upload.object_name}")
            self.logger.info(f"Upload ID: {upload.upload_id}")
            self.logger.info(f"Number of parts: {len(upload.parts)}")
            
            start_time = time.time()
            
            # 1. 准备parts列表
            prep_start = time.time()
            parts = []
            for part_number, etag in sorted(upload.parts):
                parts.append(Part(
                    part_number=part_number,
                    etag=etag.strip('"')
                ))
                self.logger.debug(f"Part {part_number}: ETag={etag}")
            
            prep_time = time.time() - prep_start
            self.logger.info(f"Parts preparation took {prep_time:.2f}s")
            
            # 2. 发送完成请求
            self.logger.info("Sending completion request to server...")
            completion_start = time.time()
            
            try:
                result = self.client._complete_multipart_upload(
                    self.config.bucket_name,
                    upload.object_name,
                    upload.upload_id,
                    parts
                )
            except Exception as e:
                self.logger.error(f"Server-side completion failed: {e}")
                raise
            
            completion_time = time.time() - completion_start
            self.logger.info(f"Server-side completion took {completion_time:.2f}s")
            
            # 3. 获取URL
            url_start = time.time()
            url = self.get_public_url(upload.object_name)
            url_time = time.time() - url_start
            
            total_time = time.time() - start_time
            self.logger.info(f"\nComplete Multipart Upload Timing:")
            self.logger.info(f"  • Parts Preparation: {prep_time:.2f}s")
            self.logger.info(f"  • Server Completion: {completion_time:.2f}s")
            self.logger.info(f"  • URL Generation: {url_time:.2f}s")
            self.logger.info(f"  • Total Time: {total_time:.2f}s")
            
            return url

        except Exception as e:
            self.logger.error(f"Failed to complete multipart upload: {e}")
            self.logger.error(f"Exception type: {type(e)}")
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            raise OSSError(f"Failed to complete multipart upload: {e}")

    def abort_multipart_upload(self, upload: MultipartUpload) -> None:
        """取消分片上传"""
        try:
            # 使用 MinIO 的原生取消上传
            self.client.abort_multipart_upload(
                self.config.bucket_name,
                upload.object_name,
                upload.upload_id
            )
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

    def copy_object(self, source_key: str, target_key: str) -> str:
        """复制对象
        Args:
            source_key: 源对象路径
            target_key: 目标对象路径
        Returns:
            str: 目标对象的URL
        """
        try:
            # 1. 获取源对象信息
            source_stat = self.client.stat_object(
                bucket_name=self.config.bucket_name,
                object_name=source_key
            )
            
            # 2. 获取源对象数据
            data = self.client.get_object(
                bucket_name=self.config.bucket_name,
                object_name=source_key
            )
            
            # 3. 上传到位置
            result = self.client.put_object(
                bucket_name=self.config.bucket_name,
                object_name=target_key,
                data=data,
                length=source_stat.size,  # 使用源文件的大小
                content_type=source_stat.content_type  # 保持内容类型一致
            )
            
            return self.get_public_url(target_key)
            
        except S3Error as e:
            if 'NoSuchKey' in str(e):
                raise ObjectNotFoundError(f"Source object not found: {source_key}")
            elif 'NoSuchBucket' in str(e):
                raise BucketNotFoundError(f"Bucket not found: {self.config.bucket_name}")
            raise OSSError(f"Failed to copy object: {str(e)}")

    def rename_object(self, source_key: str, target_key: str) -> str:
        """重命名对象（复制后删除源对象）
        Args:
            source_key: 源对象路径
            target_key: 目标对象路径
        Returns:
            str: 新对象的URL
        """
        try:
            # 1. 复制对象
            new_url = self.copy_object(source_key, target_key)
            
            # 2. 删除源对象
            self.delete_file(source_key)
            
            return new_url
            
        except S3Error as e:
            raise OSSError(f"Failed to rename object: {str(e)}")

    def rename_folder(self, source_prefix: str, target_prefix: str) -> None:
        """重命名文件夹（移动所有文件到新路径）
        Args:
            source_prefix: 源文件夹路径（以/结尾）
            target_prefix: 目标文件夹路径（以/结尾）
        """
        try:
            # 确保路径以/结尾
            if not source_prefix.endswith('/'):
                source_prefix += '/'
            if not target_prefix.endswith('/'):
                target_prefix += '/'
            
            # 列出源文件夹中的所有对象
            objects = self.client.list_objects(
                self.config.bucket_name,
                prefix=source_prefix,
                recursive=True
            )
            
            found = False
            for obj in objects:
                found = True
                old_key = obj.object_name
                # 构建新的对象键
                new_key = target_prefix + old_key[len(source_prefix):]
                
                # 复制到新位置
                self.copy_object(old_key, new_key)
                
                # 删除原对象
                self.delete_file(old_key)
                
            if not found:
                raise ObjectNotFoundError(f"Source folder not found: {source_prefix}")
            
        except S3Error as e:
            raise OSSError(f"Failed to rename folder: {str(e)}")

    def object_exists(self, object_name: str) -> bool:
        """查对象是否存在"""
        try:
            self.client.stat_object(
                bucket_name=self.config.bucket_name,
                object_name=object_name
            )
            return True
        except Exception as e:
            # Catch any exception, not just S3Error
            return False

    def get_object_size(self, object_name: str) -> int:
        """获取对象大小
        Args:
            object_name: 对象名称
        Returns:
            int: 对象大小（字节）
        """
        try:
            stat = self.client.stat_object(
                bucket_name=self.config.bucket_name,
                object_name=object_name
            )
            return stat.size
        except S3Error as e:
            if 'NoSuchKey' in str(e):
                raise ObjectNotFoundError(f"Object not found: {object_name}")
            raise OSSError(f"Failed to get object size: {str(e)}")