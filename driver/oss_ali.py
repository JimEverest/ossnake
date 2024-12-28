from typing import Optional, BinaryIO, List, Dict
import oss2
from oss2.models import PartInfo
from oss2 import Auth, Bucket, ObjectIterator
from oss2.exceptions import OssError
import os
from datetime import datetime
import logging
from urllib.parse import urlparse
import json

from .types import OSSConfig, ProgressCallback, MultipartUpload
from .base_oss import BaseOSSClient
from .exceptions import (
    OSSError, ConnectionError, AuthenticationError, 
    ObjectNotFoundError, BucketNotFoundError,
    UploadError, DownloadError
)

class AliyunOSSClient(BaseOSSClient):
    """阿里云OSS客户端实现"""
    
    logger = logging.getLogger(__name__)

    def __init__(self, config: OSSConfig):
        """初始化阿里云OSS客户端"""
        super().__init__(config)  # 调用基类的初始化方法
        self._init_client()

    def _init_client(self) -> None:
        """初始化OSS客户端"""
        try:
            # 配置代理
            if hasattr(self.config, 'proxy') and self.config.proxy:
                proxy_info = urlparse(self.config.proxy)
                # 创建代理配置
                proxies = {
                    'http': self.config.proxy,
                    'https': self.config.proxy
                }
                # 设置环境变量
                os.environ['HTTP_PROXY'] = self.config.proxy
                os.environ['HTTPS_PROXY'] = self.config.proxy
                self.logger.info(f"Using proxy: {self.config.proxy}")
            
            # 创建认证对象
            self.auth = Auth(self.config.access_key, self.config.secret_key)
            
            # 创建Bucket对象，添加代理配置
            self.bucket = Bucket(
                self.auth,
                self.config.endpoint,
                self.config.bucket_name,
                connect_timeout=30,
                app_name='ossnake',
                enable_crc=True,
                proxies=proxies if 'proxies' in locals() else None
            )
        except Exception as e:
            raise ConnectionError(f"Failed to initialize Aliyun OSS client: {str(e)}")

    def _upload_file(self, local_file: str, object_name: str, progress_callback: Optional[ProgressCallback] = None) -> str:
        """实际的文件上传实现"""
        try:
            self.bucket.put_object_from_file(object_name, local_file, progress_callback=progress_callback)
            return self.get_public_url(object_name)
        except OssError as e:
            raise UploadError(f"Failed to upload file {local_file}: {str(e)}")

    def download_file(self, object_name: str, local_file: str, progress_callback: Optional[ProgressCallback] = None) -> None:
        """下载文件"""
        try:
            self.bucket.get_object_to_file(object_name, local_file, progress_callback=progress_callback)
        except OssError as e:
            raise DownloadError(f"Failed to download file {object_name}: {str(e)}")

    def delete_file(self, object_name: str) -> None:
        """删除文件"""
        try:
            self.bucket.delete_object(object_name)
        except OssError as e:
            raise OSSError(f"Failed to delete file {object_name}: {str(e)}")

    def list_objects(self, prefix: str = '', recursive: bool = True) -> List[Dict]:
        """列出对象"""
        try:
            objects = []
            for obj in ObjectIterator(self.bucket, prefix=prefix):
                objects.append({
                    'name': obj.key,
                    'size': obj.size,
                    'last_modified': obj.last_modified,
                    'type': 'file'
                })
            return objects
        except OssError as e:
            raise OSSError(f"Failed to list objects: {str(e)}")

    def get_presigned_url(self, object_name: str, expires: int = 3600) -> str:
        """获取预签名URL"""
        try:
            return self.bucket.sign_url('GET', object_name, expires)
        except OssError as e:
            raise OSSError(f"Failed to get presigned url: {str(e)}")

    def get_public_url(self, object_name: str) -> str:
        """获取公共访问URL"""
        return f"https://{self.config.bucket_name}.{self.config.endpoint}/{object_name}"

    def create_folder(self, folder_name: str) -> None:
        """创建文件夹"""
        if not folder_name.endswith('/'):
            folder_name += '/'
        try:
            self.bucket.put_object(folder_name, '')
        except OssError as e:
            raise OSSError(f"Failed to create folder: {str(e)}")

    def move_object(self, source: str, destination: str) -> None:
        """移动/重命名对象"""
        try:
            self.bucket.copy_object(self.config.bucket_name, source, destination)
            self.bucket.delete_object(source)
        except OssError as e:
            raise OSSError(f"Failed to move object: {str(e)}")

    def list_buckets(self) -> List[Dict]:
        """列出所有可用的存储桶"""
        try:
            service = oss2.Service(self.auth, self.config.endpoint)
            buckets = []
            for bucket in service.list_buckets().buckets:
                buckets.append({
                    'name': bucket.name,
                    'creation_date': bucket.creation_date,
                    'location': bucket.location
                })
            return buckets
        except OssError as e:
            raise OSSError(f"Failed to list buckets: {str(e)}")

    def set_bucket_policy(self, policy: Dict) -> None:
        """设置存储桶策略"""
        try:
            self.bucket.put_bucket_policy(json.dumps(policy))
        except OssError as e:
            raise OSSError(f"Failed to set bucket policy: {str(e)}")

    def init_multipart_upload(self, object_name: str) -> MultipartUpload:
        """初始化分片上传"""
        try:
            upload = self.bucket.init_multipart_upload(object_name)
            return MultipartUpload(
                object_name=object_name,
                upload_id=upload.upload_id
            )
        except OssError as e:
            raise OSSError(f"Failed to init multipart upload: {str(e)}")

    def upload_part(self, upload: MultipartUpload, part_number: int, data: bytes) -> str:
        """上传分片"""
        try:
            result = self.bucket.upload_part(
                upload.object_name,
                upload.upload_id,
                part_number,
                data
            )
            return result.etag
        except OssError as e:
            raise OSSError(f"Failed to upload part: {str(e)}")

    def complete_multipart_upload(self, upload: MultipartUpload) -> str:
        """完成分片上传"""
        try:
            parts = []
            for part_num, etag in upload.parts:
                parts.append(PartInfo(part_num, etag))
            self.bucket.complete_multipart_upload(
                upload.object_name,
                upload.upload_id,
                parts
            )
            return self.get_public_url(upload.object_name)
        except OssError as e:
            raise OSSError(f"Failed to complete multipart upload: {str(e)}")

    def abort_multipart_upload(self, upload: MultipartUpload) -> None:
        """取消分片上传"""
        try:
            self.bucket.abort_multipart_upload(
                upload.object_name,
                upload.upload_id
            )
        except OssError as e:
            raise OSSError(f"Failed to abort multipart upload: {str(e)}")

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
            # 设置headers
            headers = {}
            if content_type:
                headers['Content-Type'] = content_type
            
            # 使用put_object进行流式上传
            self.bucket.put_object(
                object_name,
                input_stream,
                headers=headers
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
            object_stream = self.bucket.get_object(object_name)
            
            # 获取文件大小
            file_size = object_stream.content_length
            downloaded = 0
            
            # 流读取和写入
            while True:
                chunk = object_stream.read(chunk_size)
                if not chunk:
                    break
                
                output_stream.write(chunk)
                downloaded += len(chunk)
                
                if progress_callback:
                    progress_callback(downloaded)
                
            # 确保所有数据都写入
            output_stream.flush()
            
        except Exception as e:
            raise OSSError(f"Failed to download stream: {str(e)}")

    def object_exists(self, object_name: str) -> bool:
        """检查对象是否存在"""
        try:
            self.bucket.get_object_meta(object_name)
            return True
        except oss2.exceptions.NoSuchKey:
            return False
        except OssError as e:
            raise OSSError(f"Failed to check object existence: {str(e)}")

    def get_object_size(self, object_name: str) -> int:
        """获取对象大小"""
        try:
            meta = self.bucket.get_object_meta(object_name)
            return meta.content_length
        except OssError as e:
            raise OSSError(f"Failed to get object size: {str(e)}")

    def copy_object(self, source_object: str, target_object: str) -> str:
        """复制对象"""
        try:
            self.bucket.copy_object(self.config.bucket_name, source_object, target_object)
            return self.get_public_url(target_object)
        except OssError as e:
            raise OSSError(f"Failed to copy object: {str(e)}")

    def rename_object(self, source_object: str, target_object: str) -> str:
        """重命名对象"""
        self.copy_object(source_object, target_object)
        self.delete_file(source_object)
        return self.get_public_url(target_object)

    def rename_folder(self, source_prefix: str, target_prefix: str) -> None:
        """重命名文件夹"""
        if not source_prefix.endswith('/'):
            source_prefix += '/'
        if not target_prefix.endswith('/'):
            target_prefix += '/'

        objects = self.list_objects(prefix=source_prefix)
        for obj in objects:
            new_object_name = obj['name'].replace(source_prefix, target_prefix, 1)
            self.rename_object(obj['name'], new_object_name)

    def get_object_info(self, object_name: str) -> Dict:
        """获取对象信息"""
        try:
            # 使用 head_object 获取对象元数据
            object_meta = self.bucket.head_object(object_name)
            
            return {
                'size': object_meta.content_length,
                'type': object_meta.content_type,
                'last_modified': object_meta.last_modified,
                'etag': object_meta.etag.strip('"')
            }
        except Exception as e:
            if 'NoSuchKey' in str(e):
                raise ObjectNotFoundError(f"Object not found: {object_name}")
            raise OSSError(f"Failed to get object info: {str(e)}")

    def upload_file(self, local_file: str, object_name: str, progress_callback=None) -> str:
        """上传文件"""
        try:
            # 创建进度回调包装器
            if progress_callback:
                file_size = os.path.getsize(local_file)
                
                def callback(bytes_consumed, total_bytes):
                    progress_callback(bytes_consumed)
            else:
                callback = None

            # 执行上传
            self.bucket.put_object_from_file(
                object_name,
                local_file,
                progress_callback=callback
            )
            
            return self.get_public_url(object_name)
            
        except Exception as e:
            raise UploadError(f"Failed to upload file: {str(e)}")
