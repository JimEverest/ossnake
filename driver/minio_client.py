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
import json

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
        super().__init__(config)  # 调用基类的初始化方法
        self.logger = logging.getLogger(__name__)
        
        try:
            # 配置代理
            http_client_args = {
                'timeout': urllib3.Timeout.DEFAULT_TIMEOUT,
                'maxsize': 10,
                'retries': urllib3.Retry(
                    total=3,
                    backoff_factor=0.2,
                    status_forcelist=[500, 502, 503, 504]
                )
            }
            
            # 根据是否有代理使用不同的HTTP客户端
            if self.proxy_settings and (self.proxy_settings.get('http') or self.proxy_settings.get('https')):
                proxy_url = self.proxy_settings.get('https') or self.proxy_settings.get('http')
                http_client = urllib3.ProxyManager(
                    proxy_url,
                    **http_client_args
                )
                self.logger.info(f"Using proxy: {proxy_url}")
            else:
                http_client = urllib3.PoolManager(**http_client_args)
            
            # 创建MinIO客户端
            self.client = Minio(
                endpoint=config.endpoint,
                access_key=config.access_key,
                secret_key=config.secret_key,
                secure=config.secure,
                http_client=http_client
            )
            self.connected = True
            self.logger.info(f"MinIO client initialized with endpoint: {config.endpoint}")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize MinIO client: {str(e)}")
            raise ConnectionError(f"Failed to connect to MinIO: {str(e)}")

    def _init_client(self) -> None:
        """初始化MinIO客户端"""
        try:
            # 创建 HTTP 客户端配置
            http_client = self._create_http_client_config()
            
            # 创建MinIO客户端
            self.client = Minio(
                self.config.endpoint,
                access_key=self.config.access_key,
                secret_key=self.config.secret_key,
                secure=self.config.secure,
                http_client=http_client
            )
            
            # 测试连接
            self.client.list_buckets()
            self.logger.info("Successfully connected to MinIO server")
            
        except Exception as e:
            self.logger.error(f"Failed to connect to MinIO server: {str(e)}")
            raise ConnectionError(f"Failed to connect to MinIO server: {str(e)}")
    
    def _create_http_client_config(self):
        """创建HTTP客户端配置"""
        # 基本的超时和重试配置
        timeout = urllib3.Timeout(connect=5.0, read=60.0)
        retries = urllib3.Retry(
            total=3,
            backoff_factor=0.2,
            status_forcelist=[500, 502, 503, 504]
        )
        
        # 检查是否需要配置代理
        if hasattr(self.config, 'proxy') and self.config.proxy:
            return urllib3.ProxyManager(
                self.config.proxy,
                timeout=timeout,
                maxsize=8,
                retries=retries
            )
        else:
            return urllib3.PoolManager(
                timeout=timeout,
                maxsize=8,
                retries=retries
            )

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

    def download_file(self, object_name: str, local_path: str, progress_callback=None):
        """下载文件"""
        try:
            # 确保目标目录存在
            os.makedirs(os.path.dirname(os.path.abspath(local_path)), exist_ok=True)
            
            # 获取文件大小
            try:
                stat = self.client.stat_object(self.config.bucket_name, object_name)
                total_size = stat.size
            except Exception as e:
                self.logger.error(f"Failed to get object stats: {e}")
                total_size = 0
            
            # 创建进度回调包装器
            if progress_callback and total_size > 0:
                class ProgressWrapper:
                    def __init__(self):
                        self._transferred = 0
                        
                    def __call__(self, chunk_size):
                        self._transferred += int(chunk_size)  # 确保是整数
                        progress_callback(self._transferred, total_size)
                    
                    def update(self, chunk_size):
                        """MinIO需要这个方法"""
                        self.__call__(chunk_size)
                        
                    def set_meta(self, **kwargs):
                        """MinIO需要这个方法"""
                        pass
                
                callback = ProgressWrapper()
            else:
                callback = None
            
            # 执行下载
            self.client.fget_object(
                bucket_name=self.config.bucket_name,
                object_name=object_name,
                file_path=local_path,
                progress=callback
            )
            
        except Exception as e:
            if os.path.exists(local_path):
                try:
                    os.remove(local_path)  # 清理未完成的文件
                except:
                    pass
            raise OSSError(f"Failed to download file: {str(e)}")

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
                # 保持原始名称，不做任何转换
                name = str(item.object_name)  # 确保是字符串类型
                
                if item.is_dir:
                    objects.append({
                        'name': name,  # 保持原始名称
                        'type': 'directory',
                        'size': 0,
                        'last_modified': None
                    })
                else:
                    objects.append({
                        'name': name,  # 保持原始名称
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

    def create_folder(self, folder_path: str) -> None:
        """创建文件夹（在对象存储中创建一个空对象）
        Args:
            folder_path: 文件夹路径（以/结尾）
        """
        try:
            self.logger.debug(f"Creating folder: {folder_path}")
            
            # 确保路径以/结尾
            if not folder_path.endswith('/'):
                folder_path += '/'
            
            # 创建一个空的字节流作为文件夹标记
            empty_data = b''
            
            # 上传空对象
            self.client.put_object(
                bucket_name=self.config.bucket_name,
                object_name=folder_path,  # 文件夹路径必须以/结尾
                data=BytesIO(empty_data),
                length=0,
                content_type='application/x-directory'  # 设置特殊的内容类型
            )
            
            self.logger.debug(f"Folder created: {folder_path}")
            
        except S3Error as e:
            self.logger.error(f"Failed to create folder: {str(e)}")
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

    def upload_file(self, local_file: str, object_name: str, progress_callback=None) -> str:
        """上传文件"""
        try:
            # 创建进度回调包装器
            if progress_callback:
                file_size = os.path.getsize(local_file)
                
                class ProgressWrapper:
                    def __init__(self):
                        self._seen_so_far = 0
                        
                    def __call__(self, size):
                        self._seen_so_far += size
                        progress_callback(self._seen_so_far)
                        
                    def update(self, size):
                        self.__call__(size)
                        
                    def set_meta(self, **kwargs):
                        pass
                
                callback = ProgressWrapper()
            else:
                callback = None

            # 执行上传
            self.client.fput_object(
                bucket_name=self.config.bucket_name,
                object_name=object_name,
                file_path=local_file,
                progress=callback
            )
            
            return self.get_public_url(object_name)
            
        except Exception as e:
            raise UploadError(f"Failed to upload file: {str(e)}")

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
            
            # 创建一个单的进度跟踪器
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
            self.logger.info(f"- Parts Preparation: {prep_time:.2f}s")
            self.logger.info(f"- Server Completion: {completion_time:.2f}s")
            self.logger.info(f"- URL Generation: {url_time:.2f}s")
            self.logger.info(f"- Total Time: {total_time:.2f}s")
            
            return url
            
        except Exception as e:
            self.logger.error(f"Failed to complete multipart upload: {e}")
            self.logger.error(f"Exception type: {type(e)}")
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


    def upload_stream(self, input_stream, object_name: str, content_type: str = None) -> str:
        """流式上传文件
        Args:
            input_stream: 输入流（需要支持read方法）
            object_name: 对象名称
            content_type: 内容类型
        Returns:
            str: 对象的URL
        """
        try:
            # 获取流的长度
            if hasattr(input_stream, 'seek') and hasattr(input_stream, 'tell'):
                # 如果流支持seek和tell，获取长度
                current_pos = input_stream.tell()
                input_stream.seek(0, os.SEEK_END)
                length = input_stream.tell()
                input_stream.seek(current_pos)  # 恢复原始位置
            else:
                # 如果不支持，读取到内存中
                data = input_stream.read()
                length = len(data)
                input_stream = BytesIO(data)
            
            # 使用put_object进行流式上传
            self.client.put_object(
                bucket_name=self.config.bucket_name,
                object_name=object_name,
                data=input_stream,
                length=length,  # 添加长度参数
                content_type=content_type or 'application/octet-stream'
            )
            
            return self.get_public_url(object_name)
            
        except Exception as e:
            raise OSSError(f"Failed to upload stream: {str(e)}")

    def download_stream(self, object_name: str, output_stream, chunk_size=1024*1024, progress_callback=None):
        """流式下载文件
        Args:
            object_name: 对象名称
            output_stream: 输出流（需要支持write方法）
            chunk_size: 分块大小（默认1MB）
            progress_callback: 进度回调函数
        """
        try:
            # 获取对象
            response = self.client.get_object(
                bucket_name=self.config.bucket_name,
                object_name=object_name
            )
            
            # 获取文件大小
            file_size = response.headers.get('content-length', 0)
            downloaded = 0
            
            # 流式读取和写入
            for chunk in response.stream(chunk_size):
                output_stream.write(chunk)
                downloaded += len(chunk)
                
                if progress_callback:
                    progress_callback(downloaded)
                    
            # 确保所有数据都写入
            output_stream.flush()
            
        except Exception as e:
            raise OSSError(f"Failed to download stream: {str(e)}") 
        
        
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
        """对象是否存在"""
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

    def get_object_info(self, object_name: str) -> Dict:
        """获取对象信息"""
        try:
            # 使用 stat_object 获取对象信息
            stat = self.client.stat_object(
                bucket_name=self.config.bucket_name,
                object_name=object_name
            )
            
            return {
                'size': stat.size,
                'type': stat.content_type,
                'last_modified': stat.last_modified,
                'etag': stat.etag.strip('"')
            }
        except S3Error as e:
            if 'NoSuchKey' in str(e):
                raise ObjectNotFoundError(f"Object not found: {object_name}")
            raise OSSError(f"Failed to get object info: {str(e)}")

    def put_object(self, object_name: str, data: bytes, content_type: str = None) -> str:
        """直接上传数据
        Args:
            object_name: 对象名称
            data: 要上传的数据
            content_type: 内容类型
        Returns:
            str: 对象的URL
        """
        try:
            self.logger.debug(f"Starting put_object to {object_name}")
            
            # 使用 MinIO SDK 的 put_object 方法
            self.client.put_object(
                bucket_name=self.config.bucket_name,
                object_name=object_name,
                data=BytesIO(data),
                length=len(data),
                content_type=content_type or 'application/octet-stream'
            )
            
            self.logger.debug(f"Put object completed: {object_name}")
            return self.get_public_url(object_name)
            
        except S3Error as e:
            self.logger.error(f"Put object failed: {str(e)}")
            raise UploadError(f"Upload failed: {str(e)}")