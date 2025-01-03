import logging
from typing import List, Optional, BinaryIO, Dict
import boto3
import os
from datetime import datetime, timedelta
from botocore.exceptions import ClientError
from botocore.config import Config
from urllib.parse import urlparse
from boto3.exceptions import S3UploadFailedError
from boto3.s3.transfer import TransferConfig
import threading

from .types import OSSConfig, ProgressCallback, MultipartUpload
from .base_oss import BaseOSSClient
from .exceptions import (
    OSSError, ConnectionError, AuthenticationError, 
    ObjectNotFoundError, BucketNotFoundError, 
    UploadError, DownloadError, TransferError
)

class AWSS3Client(BaseOSSClient):
    """
    AWS S3客户端实现
    
    实现了BaseOSSClient定义的所有抽象方法，提供完整的AWS S3操作接口。
    包含错误处理、重试机制和详细的操作日志。
    """
    logger = logging.getLogger(__name__)

    def __init__(self, config: OSSConfig):
        """初始化AWS S3客户端"""
        super().__init__(config)  # 调用基类的初始化方法
        
    def _init_client(self) -> None:
        """初始化AWS S3客户端"""
        try:
            # 创建会话配置
            session_config = {
                'aws_access_key_id': self.config.access_key,
                'aws_secret_access_key': self.config.secret_key,
                'region_name': self.config.region
            }
            
            # 创建会话
            self.session = boto3.Session(**session_config)
            
            # 创建客户端配置
            client_config = Config(
                retries=dict(max_attempts=3)
            )
            
            # 设置代理配置
            if self.proxy_settings:
                self.logger.info(f"Configuring AWS S3 client with proxy: {self.proxy_settings}")
                client_config = Config(
                    proxies=self.proxy_settings,
                    retries=dict(max_attempts=3)
                )
            else:
                self.logger.info("AWS S3 client initialized without proxy")
            
            # 创建S3客户端
            self.client = self.session.client(
                's3',
                endpoint_url=self.config.endpoint if self.config.endpoint else None,
                config=client_config,
                use_ssl=self.config.secure,
                verify=False
            )
            
            # 创建S3资源对象（用于高级操作）
            self.resource = self.session.resource(
                's3',
                endpoint_url=self.config.endpoint if self.config.endpoint else None,
                config=client_config
            )
            
            # 创建Bucket引用
            if self.config.bucket_name:
                self.bucket = self.resource.Bucket(self.config.bucket_name)
            
            self.connected = True
            self.logger.info(f"AWS S3 client initialized with endpoint: {self.config.endpoint}")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize AWS S3 client: {str(e)}")
            raise ConnectionError(f"Failed to connect to AWS S3: {str(e)}")

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
            
            # 创建进度回调
            if progress_callback:
                total_size = os.path.getsize(local_file)
                start_time = datetime.now()
                
                def progress_handler(bytes_amount):
                    try:
                        elapsed = (datetime.now() - start_time).total_seconds()
                        speed = bytes_amount / elapsed if elapsed > 0 else 0
                        progress_callback.on_progress(
                            bytes_amount,
                            total_size,
                            start_time,
                            speed
                        )
                    except Exception as e:
                        if isinstance(e, TransferError):
                            raise
                        self.logger.warning(f"Progress callback failed: {e}")
            else:
                progress_handler = None
            
            try:
                self.client.upload_file(
                    local_file,
                    self.config.bucket_name,
                    object_name,
                    Callback=progress_handler,
                    ExtraArgs={'ContentType': self._get_content_type(local_file)}
                )
                return self.get_public_url(object_name)
                
            except ClientError as e:
                error = e.response['Error']
                error_code = error['Code']
                error_msg = error['Message']
                
                if error_code in ('AccessDenied', 'InvalidAccessKeyId', 'SignatureDoesNotMatch'):
                    self._handle_auth_error(e)
                elif error_code == 'NoSuchBucket':
                    raise BucketNotFoundError(f"Bucket {self.config.bucket_name} not found")
                elif error_code == 'NoSuchKey':
                    raise ObjectNotFoundError(f"Object {object_name} not found")
                elif 'RequestTimeout' in error_code:
                    self._handle_network_error(e)
                else:
                    raise UploadError(f"Upload failed: {error_msg}")
            except S3UploadFailedError as e:
                if "InvalidAccessKeyId" in str(e):
                    raise UploadError(f"Upload failed: {str(e)}") from AuthenticationError("Invalid credentials or access denied")
                raise UploadError(f"Upload failed: {str(e)}")
                
        except Exception as e:
            if isinstance(e, (BucketNotFoundError, AuthenticationError, ObjectNotFoundError, UploadError)):
                raise
            raise UploadError(f"Upload failed: {str(e)}")

    def upload_file(self, local_file: str, object_name: str, progress_callback=None) -> str:
        """Upload a file to S3"""
        try:
            # 创建一个 S3 传输配置
            config = TransferConfig(
                multipart_threshold=8 * 1024 * 1024,  # 8MB
                max_concurrency=10,
                multipart_chunksize=8 * 1024 * 1024,  # 8MB
                use_threads=True
            )

            # 创建一个进度回调包装器
            if progress_callback:
                file_size = os.path.getsize(local_file)
                
                class ProgressPercentage:
                    def __init__(self):
                        self._size = file_size
                        self._seen_so_far = 0
                        self._lock = threading.Lock()

                    def __call__(self, bytes_amount):
                        with self._lock:
                            self._seen_so_far += bytes_amount
                            progress_callback(self._seen_so_far)

                callback = ProgressPercentage()
            else:
                callback = None

            # 上传文件
            self.client.upload_file(
                local_file,
                self.config.bucket_name,
                object_name,
                Config=config,
                Callback=callback
            )

            # 返回文件的URL
            return self.get_public_url(object_name)

        except Exception as e:
            self.logger.error(f"Failed to upload file {local_file}: {str(e)}")
            raise UploadError(f"Failed to upload file {local_file}: {str(e)}")

    def upload_stream(
        self,
        stream: BinaryIO,
        object_name: str,
        content_type: Optional[str] = None
    ) -> str:
        """从流中上传数据到S3
        Args:
            stream: 数据流
            object_name: 对象名称
            content_type: 内容类型
        Returns:
            str: 对象的URL
        """
        try:
            self.logger.debug(f"Starting stream upload to {object_name}")
            
            # 确保流指针在开始位置
            if hasattr(stream, 'seek'):
                stream.seek(0)
            
            # 上传文件
            self.client.upload_fileobj(
                stream,
                self.config.bucket_name,
                object_name,
                ExtraArgs={
                    'ContentType': content_type or 'application/octet-stream'
                }
            )
            
            self.logger.debug(f"Stream upload completed: {object_name}")
            return self.get_public_url(object_name)
            
        except ClientError as e:
            error = e.response['Error']
            error_code = error['Code']
            error_msg = error['Message']
            
            self.logger.error(f"Stream upload failed: {error_code} - {error_msg}")
            
            if error_code in ('AccessDenied', 'InvalidAccessKeyId', 'SignatureDoesNotMatch'):
                raise AuthenticationError(error_msg)
            elif error_code == 'NoSuchBucket':
                raise BucketNotFoundError(error_msg)
            else:
                raise UploadError(f"Upload failed: {error_msg}")
                
        except Exception as e:
            self.logger.error(f"Unexpected error during stream upload: {str(e)}")
            raise UploadError(f"Upload failed: {str(e)}")

    def download_file(self, remote_path: str, local_path: str, progress_callback=None):
        """下载文件"""
        try:
            # 确保目标目录存在
            os.makedirs(os.path.dirname(os.path.abspath(local_path)), exist_ok=True)
            
            # 获取文件总大小
            total_size = self.get_object_size(remote_path)
            transferred = 0
            
            # 创建进度回调包装器
            config = TransferConfig(
                use_threads=True,
                max_concurrency=10,
                multipart_threshold=1024 * 1024 * 8,  # 8MB
                multipart_chunksize=1024 * 1024 * 8  # 8MB
            )
            
            if progress_callback:
                def s3_callback(bytes_amount):
                    nonlocal transferred
                    transferred += bytes_amount
                    try:
                        progress_callback(transferred, total_size)
                    except Exception as e:
                        self.logger.warning(f"Progress callback failed: {e}")
            else:
                s3_callback = None
            
            # 执行下载
            self.client.download_file(
                self.config.bucket_name,
                remote_path,
                local_path,
                Config=config,
                Callback=s3_callback
            )
            
        except Exception as e:
            raise OSSError(f"Failed to download file: {str(e)}")

    def delete_file(self, object_name: str) -> None:
        """删除文件"""
        try:
            # Check if the object exists before attempting to delete
            if not self.object_exists(object_name):
                raise ObjectNotFoundError(f"Object not found: {object_name}")

            self.client.delete_object(
                Bucket=self.config.bucket_name,
                Key=object_name
            )
        except ClientError as e:
            # If the error is not related to object existence, raise it
            if e.response['Error']['Code'] != 'NoSuchKey':
                raise OSSError(f"Failed to delete file {object_name}: {str(e)}")

    def list_objects(self, prefix: str = '', recursive: bool = True) -> List[Dict]:
        """列出对象"""
        try:
            self.logger.info(f"Listing objects with prefix '{prefix}'")
            self.logger.info(f"Using proxy: {self.proxy_settings}")
            self.logger.info(f"Endpoint: {self.config.endpoint}")
            self.logger.info(f"Region: {self.config.region}")
            
            # 记录当前环境变量
            env_proxies = {
                'HTTP_PROXY': os.environ.get('HTTP_PROXY'),
                'HTTPS_PROXY': os.environ.get('HTTPS_PROXY')
            }
            self.logger.info(f"Current proxy environment: {env_proxies}")
            
            objects = []
            paginator = self.client.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=self.config.bucket_name, Prefix=prefix)
            
            for page in pages:
                if 'Contents' in page:
                    for obj in page['Contents']:
                        if obj['Key'].endswith('/'):
                            objects.append({
                                'name': obj['Key'],
                                'type': 'folder',
                                'size': 0,
                                'last_modified': obj['LastModified']
                            })
                        else:
                            objects.append({
                                'name': obj['Key'],
                                'type': 'file',
                                'size': obj['Size'],
                                'last_modified': obj['LastModified'],
                                'etag': obj['ETag'].strip('"')
                            })
                            
            return objects
            
        except ClientError as e:
            raise ClientError(e.response, e.operation_name)

    def get_presigned_url(self, object_name: str, expires: int = 3600) -> str:
        """获取预签名URL"""
        try:
            return self.client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': self.config.bucket_name,
                    'Key': object_name
                },
                ExpiresIn=expires
            )
        except ClientError as e:
            raise ClientError(e.response, e.operation_name)

    def get_public_url(self, object_name: str) -> str:
        """获取公共访问URL"""
        if self.config.endpoint:
            endpoint = urlparse(self.config.endpoint).netloc
            return f"https://{self.config.bucket_name}.{endpoint}/{object_name}"
        else:
            return f"https://{self.config.bucket_name}.s3.{self.config.region}.amazonaws.com/{object_name}"

    def create_folder(self, folder_name: str) -> None:
        """创建文件夹（通过创建空对象实现）"""
        if not folder_name.endswith('/'):
            folder_name += '/'
        try:
            self.client.put_object(
                Bucket=self.config.bucket_name,
                Key=folder_name,
                Body=''
            )
        except ClientError as e:
            raise ClientError(e.response, e.operation_name)

    def move_object(self, source: str, destination: str) -> None:
        """移动/重命名对象"""
        try:
            # 使用resource进行复制操作
            copy_source = {
                'Bucket': self.config.bucket_name,
                'Key': source
            }
            self.bucket.copy(copy_source, destination)
            
            # 删除源对象
            self.client.delete_object(
                Bucket=self.config.bucket_name,
                Key=source
            )
        except ClientError as e:
            raise ClientError(e.response, e.operation_name)

    def list_buckets(self) -> List[Dict]:
        """列出所有可用的存储"""
        try:
            response = self.client.list_buckets()
            return [{
                'name': bucket['Name'],
                'creation_date': bucket['CreationDate'],
                'owner': response['Owner'].get('DisplayName', 'Unknown')
            } for bucket in response['Buckets']]
        except ClientError as e:
            error = e.response['Error']
            if error['Code'] == 'AccessDenied':
                raise AuthenticationError(error['Message'], code=error['Code'])
            elif error['Code'] == 'NoSuchBucket':
                raise BucketNotFoundError(error['Message'], code=error['Code'])
            else:
                raise OSSError(error['Message'], code=error['Code'])

    def set_bucket_policy(self, policy: Dict) -> None:
        """设置存储桶策略"""
        try:
            self.client.put_bucket_policy(
                Bucket=self.config.bucket_name,
                Policy=str(policy)
            )
        except ClientError as e:
            raise ClientError(e.response, e.operation_name)

    def _get_content_type(self, filename: str) -> str:
        """根据文件扩展名获取内容类型"""
        import mimetypes
        content_type, _ = mimetypes.guess_type(filename)
        return content_type or 'application/octet-stream' 

    def init_multipart_upload(self, object_name: str) -> MultipartUpload:
        """初始化分片上传"""
        try:
            response = self.client.create_multipart_upload(
                Bucket=self.config.bucket_name,
                Key=object_name
            )
            return MultipartUpload(
                object_name=object_name,
                upload_id=response['UploadId']
            )
        except ClientError as e:
            raise ClientError(e.response, e.operation_name)

    def upload_part(self, upload: MultipartUpload, part_number: int, data: bytes) -> str:
        """上传分片，返回ETag"""
        try:
            response = self.client.upload_part(
                Bucket=self.config.bucket_name,
                Key=upload.object_name,
                UploadId=upload.upload_id,
                PartNumber=part_number,
                Body=data
            )
            return response['ETag']
        except ClientError as e:
            raise ClientError(e.response, e.operation_name)

    def complete_multipart_upload(self, upload: MultipartUpload) -> str:
        """完成分片上传，返回文件URL"""
        try:
            parts = [{
                'PartNumber': part_number,
                'ETag': etag
            } for part_number, etag in sorted(upload.parts)]
            
            self.client.complete_multipart_upload(
                Bucket=self.config.bucket_name,
                Key=upload.object_name,
                UploadId=upload.upload_id,
                MultipartUpload={'Parts': parts}
            )
            
            return self.get_public_url(upload.object_name)
            
        except ClientError as e:
            raise ClientError(e.response, e.operation_name)

    def abort_multipart_upload(self, upload: MultipartUpload) -> None:
        """取消分片上传"""
        try:
            self.client.abort_multipart_upload(
                Bucket=self.config.bucket_name,
                Key=upload.object_name,
                UploadId=upload.upload_id
            )
        except ClientError as e:
            raise ClientError(e.response, e.operation_name)

    def copy_object(self, source_key: str, target_key: str) -> str:
        """复制对象
        Args:
            source_key: 源对象路径
            target_key: 目标对象路径
        Returns:
            str: 目标对象的URL
        """
        try:
            copy_source = {
                'Bucket': self.config.bucket_name,
                'Key': source_key
            }
            
            self.client.copy_object(
                CopySource=copy_source,
                Bucket=self.config.bucket_name,
                Key=target_key
            )
            
            return self.get_public_url(target_key)
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NoSuchKey':
                raise ObjectNotFoundError(f"Source object not found: {source_key}")
            elif error_code == 'NoSuchBucket':
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
            
        except ClientError as e:
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
            paginator = self.client.get_paginator('list_objects_v2')
            for page in paginator.paginate(
                Bucket=self.config.bucket_name,
                Prefix=source_prefix
            ):
                if 'Contents' not in page:
                    raise ObjectNotFoundError(f"Source folder not found: {source_prefix}")
                    
                # 处理每个对象
                for obj in page['Contents']:
                    old_key = obj['Key']
                    # 构建新的对象键
                    new_key = target_prefix + old_key[len(source_prefix):]
                    
                    # 复制到新位置
                    self.copy_object(old_key, new_key)
                    
                    # 删除原对象
                    self.delete_file(old_key)
                    
        except ClientError as e:
            raise OSSError(f"Failed to rename folder: {str(e)}") 

    def object_exists(self, object_name: str) -> bool:
        """检查对象是否存在
        Args:
            object_name: 对象名称
        Returns:
            bool: 对象是否存在
        """
        try:
            self.client.head_object(
                Bucket=self.config.bucket_name,
                Key=object_name
            )
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return False
            raise OSSError(f"Failed to check object existence: {str(e)}")

    def get_object_size(self, object_name: str) -> int:
        """获取对象大小
        Args:
            object_name: 对象名称
        Returns:
            int: 对象大小（字节）
        """
        try:
            response = self.client.head_object(
                Bucket=self.config.bucket_name,
                Key=object_name
            )
            return response['ContentLength']
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                raise ObjectNotFoundError(f"Object not found: {object_name}")
            raise OSSError(f"Failed to get object size: {str(e)}") 

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
                Bucket=self.config.bucket_name,
                Key=object_name
            )
            
            # 获取文件大小
            file_size = response['ContentLength']
            downloaded = 0
            
            # 流式读取和写入
            body = response['Body']
            for chunk in iter(lambda: body.read(chunk_size), b''):
                output_stream.write(chunk)
                downloaded += len(chunk)
                
                if progress_callback:
                    progress_callback(downloaded)
                    
            # 确保所有数据都写入
            output_stream.flush()
            
        except Exception as e:
            raise OSSError(f"Failed to download stream: {str(e)}") 

    def get_object_info(self, object_name: str) -> Dict:
        """获取对象信息"""
        try:
            response = self.client.head_object(
                Bucket=self.config.bucket_name,
                Key=object_name
            )
            return {
                'size': response.get('ContentLength', 0),
                'type': response.get('ContentType', ''),
                'last_modified': response.get('LastModified', ''),
                'etag': response.get('ETag', '').strip('"')
            }
        except self.client.exceptions.ClientError as e:
            if e.response['Error']['Code'] == '404':
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
            
            # 上传数据
            self.client.put_object(
                Bucket=self.config.bucket_name,
                Key=object_name,
                Body=data,
                ContentType=content_type or 'application/octet-stream'
            )
            
            self.logger.debug(f"Put object completed: {object_name}")
            return self.get_public_url(object_name)
            
        except ClientError as e:
            error = e.response['Error']
            error_code = error['Code']
            error_msg = error['Message']
            
            self.logger.error(f"Put object failed: {error_code} - {error_msg}")
            raise UploadError(f"Upload failed: {error_msg}")
            
        except Exception as e:
            self.logger.error(f"Unexpected error during put_object: {str(e)}")
            raise UploadError(f"Upload failed: {str(e)}") 



    def delete_objects(self, object_names: List[str]) -> None:
        """批量删除对象"""
        try:
            objects_to_delete = [{'Key': name} for name in object_names]
            self.bucket.delete_objects(Delete={'Objects': objects_to_delete})
        except Exception as e:
            raise OSSError(f"Failed to delete objects: {str(e)}")

    def copy_objects(self, source_prefix: str, target_prefix: str) -> None:
        """批量复制对象"""
        try:
            for obj in self.bucket.objects.filter(Prefix=source_prefix):
                target_key = obj.key.replace(source_prefix, target_prefix, 1)
                self.bucket.copy({'Bucket': self.config.bucket_name, 'Key': obj.key}, target_key)
        except Exception as e:
            raise OSSError(f"Failed to copy objects: {str(e)}") 

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
        try:
            self.logger.debug(f"Getting object: {object_name}")
            response = self.client.get_object(
                Bucket=self.config.bucket_name,
                Key=object_name
            )
            return response['Body'].read()
            
        except self.client.exceptions.NoSuchKey:
            raise ObjectNotFoundError(f"Object not found: {object_name}")
            
        except Exception as e:
            self.logger.error(f"Failed to get object {object_name}: {str(e)}")
            raise OSSError(f"Failed to get object: {str(e)}") 

    def _list_objects_page(self, prefix: str = '', delimiter: str = '/', continuation_token: str = None) -> dict:
        """获取一页对象列表"""
        try:
            params = {
                'Bucket': self.config.bucket_name,
                'Prefix': prefix,
                'Delimiter': delimiter,
                'MaxKeys': 1000
            }
            
            if continuation_token:
                params['ContinuationToken'] = continuation_token
            
            response = self.client.list_objects_v2(**params)
            
            # 处理文件夹
            common_prefixes = []
            for prefix in response.get('CommonPrefixes', []):
                common_prefixes.append(prefix.get('Prefix', ''))
            
            # 处理文件
            objects = []
            for obj in response.get('Contents', []):
                objects.append({
                    'name': obj['Key'],
                    'size': obj['Size'],
                    'last_modified': obj['LastModified'].strftime('%Y-%m-%d %H:%M:%S'),
                    'type': 'file'
                })
            
            return {
                'objects': objects,
                'common_prefixes': common_prefixes,
                'next_token': response.get('NextContinuationToken')
            }
            
        except Exception as e:
            self.logger.error(f"Failed to list objects page: {str(e)}")
            raise 