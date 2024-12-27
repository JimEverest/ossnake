from typing import List, Optional, BinaryIO, Dict, Union, IO
import oss2
from oss2.exceptions import OssError
import os
import json
import logging
from datetime import datetime, timedelta
from urllib.parse import urlparse
from io import BytesIO

from .types import OSSConfig, ProgressCallback, MultipartUpload
from .base_oss import BaseOSSClient
from .exceptions import (
    OSSError, ConnectionError, AuthenticationError, 
    ObjectNotFoundError, BucketNotFoundError, 
    UploadError, DownloadError, TransferError
)

class AliyunOSSClient(BaseOSSClient):
    """阿里云OSS客户端实现"""
    
    def _init_client(self) -> None:
        """初始化OSS客户端"""
        try:
            # 创建认证对象
            self.auth = oss2.Auth(self.config.access_key, self.config.secret_key)
            
            # 创建Bucket对象
            self.bucket = oss2.Bucket(
                self.auth,
                self.config.endpoint,
                self.config.bucket_name
            )
            
            # 验证连接
            try:
                self.bucket.get_bucket_info()
                logging.info("Successfully connected to Aliyun OSS")
            except OssError as e:
                if 'InvalidAccessKeyId' in str(e):
                    raise AuthenticationError("Invalid access key")
                elif 'SignatureDoesNotMatch' in str(e):
                    raise AuthenticationError("Invalid secret key")
                elif 'NoSuchBucket' in str(e):
                    raise BucketNotFoundError(f"Bucket {self.config.bucket_name} not found")
                else:
                    raise ConnectionError(f"Failed to connect to OSS: {str(e)}")
        except Exception as e:
            raise ConnectionError(f"Failed to initialize Aliyun OSS client: {str(e)}")

    def __init__(self, config: OSSConfig):
        """初始化阿里云OSS客户端"""
        super().__init__(config)  # 这会调用父类的__init__，进而调用_init_client

    def upload_file(
        self,
        local_file: str,
        object_name: Optional[str] = None,
        progress_callback: Optional[ProgressCallback] = None
    ) -> str:
        """上传文件到OSS并返回可访问的URL"""
        if not object_name:
            object_name = os.path.basename(local_file)
            
        try:
            # 上传文件
            with open(local_file, 'rb') as f:
                self.bucket.put_object(
                    object_name,
                    f,
                    progress_callback=progress_callback
                )
            
            # 返回文件URL
            return self.get_public_url(object_name)
            
        except OssError as e:
            raise UploadError(f"Failed to upload file: {str(e)}")

    def download_file(
        self,
        object_name: str,
        local_file: str,
        progress_callback: Optional[ProgressCallback] = None
    ) -> None:
        """从OSS下载文件到本地"""
        try:
            self.bucket.get_object_to_file(
                object_name,
                local_file,
                progress_callback=progress_callback
            )
        except OssError as e:
            if 'NoSuchKey' in str(e):
                raise ObjectNotFoundError(f"Object not found: {object_name}")
            raise DownloadError(f"Failed to download file: {str(e)}")

    def get_public_url(self, object_name: str) -> str:
        """获取文件的公共访问URL"""
        return f"https://{self.config.bucket_name}.{self.config.endpoint}/{object_name}"

    def delete_file(self, object_name: str) -> None:
        """删除OSS上的文件"""
        try:
            self.bucket.delete_object(object_name)
        except OssError as e:
            raise OSSError(f"Failed to delete file: {str(e)}")

    def copy_object(self, source_key: str, target_key: str) -> str:
        """复制对象"""
        try:
            # 阿里云OSS支持服务器端复制
            self.bucket.copy_object(
                source_bucket=self.config.bucket_name,
                source_key=source_key,
                target_key=target_key
            )
            
            return self.get_public_url(target_key)
            
        except OssError as e:
            if e.status == 404:
                raise ObjectNotFoundError(f"Source object not found: {source_key}")
            elif 'NoSuchBucket' in str(e):
                raise BucketNotFoundError(f"Bucket not found: {self.config.bucket_name}")
            raise OSSError(f"Failed to copy object: {str(e)}")

    def rename_object(self, source_key: str, target_key: str) -> str:
        """重命名对象（复制后删除源对象）"""
        try:
            # 1. 复制对象
            new_url = self.copy_object(source_key, target_key)
            
            # 2. 删除源对象
            self.delete_file(source_key)
            
            return new_url
            
        except OssError as e:
            raise OSSError(f"Failed to rename object: {str(e)}")

    def rename_folder(self, source_prefix: str, target_prefix: str) -> None:
        """重命名文件夹（移动所有文件到新路径）"""
        try:
            # 确保路径以/结尾
            if not source_prefix.endswith('/'):
                source_prefix += '/'
            if not target_prefix.endswith('/'):
                target_prefix += '/'
                
            # 列出源文件夹中的所有对象
            found = False
            next_marker = ''
            while True:
                result = self.bucket.list_objects(
                    prefix=source_prefix,
                    marker=next_marker,
                    max_keys=1000
                )
                
                for obj in result.object_list:
                    found = True
                    old_key = obj.key
                    # ��建新的对象键
                    new_key = target_prefix + old_key[len(source_prefix):]
                    
                    # 复制到新位置
                    self.copy_object(old_key, new_key)
                    
                    # 删除原对象
                    self.delete_file(old_key)
                
                if not result.is_truncated:
                    break
                next_marker = result.next_marker
                
            if not found:
                raise ObjectNotFoundError(f"Source folder not found: {source_prefix}")
                
        except OssError as e:
            raise OSSError(f"Failed to rename folder: {str(e)}")

    def object_exists(self, object_name: str) -> bool:
        """检查对象是否存在"""
        try:
            self.bucket.get_object_meta(object_name)
            return True
        except OssError as e:
            if e.status == 404:
                return False
            raise OSSError(f"Failed to check object existence: {str(e)}")

    def get_object_size(self, object_name: str) -> int:
        """获取对象大小"""
        try:
            meta = self.bucket.get_object_meta(object_name)
            return int(meta.content_length)
        except OssError as e:
            if e.status == 404:
                raise ObjectNotFoundError(f"Object not found: {object_name}")
            raise OSSError(f"Failed to get object size: {str(e)}") 