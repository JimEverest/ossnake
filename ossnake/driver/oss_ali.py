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

from ossnake.driver.base_oss import BaseOSSClient
from .types import OSSConfig, ProgressCallback, MultipartUpload
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
        try:
            # 创建认证对象
            auth = oss2.Auth(config.access_key, config.secret_key)
            
            # 设置代理
            if self.proxy_settings:
                http_proxy = self.proxy_settings.get('http')
                https_proxy = self.proxy_settings.get('https')
                if http_proxy:
                    os.environ['HTTP_PROXY'] = http_proxy
                if https_proxy:
                    os.environ['HTTPS_PROXY'] = https_proxy
            
            # 创建Bucket对象
            self.client = oss2.Bucket(
                auth,
                config.endpoint,
                config.bucket_name
            )
            self.bucket = self.client  # 为了兼容性保留bucket引用
            self.connected = True
            self.logger.info(f"Aliyun OSS client initialized with endpoint: {config.endpoint}")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize Aliyun OSS client: {str(e)}")
            raise ConnectionError(f"Failed to connect to Aliyun OSS: {str(e)}")

    def _init_client(self) -> None:
        """已在__init__中实现，这里只是为了满足基类要求"""
        pass  # 实际的初始化在__init__中完成

    def _upload_file(self, local_file: str, object_name: str, progress_callback: Optional[ProgressCallback] = None) -> str:
        """实际的文件上传实现"""
        try:
            self.client.put_object_from_file(object_name, local_file, progress_callback=progress_callback)
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

    def list_objects(self, prefix: str = '', recursive: bool = False) -> List[Dict]:
        """列出对象
        Args:
            prefix: 前缀过滤
            recursive: 是否递归列出子目录，默认False表示显示文件夹结构
        Returns:
            List[Dict]: 对象列表
        """
        self.logger.info(f"Starting to list objects with prefix: '{prefix}', recursive: {recursive}")
        
        try:
            all_objects = []
            delimiter = '' if recursive else '/'
            continuation_token = None
            total_files = 0
            total_folders = 0
            
            # 如果前缀不为空且不以/结尾，添加/
            if prefix and not prefix.endswith('/'):
                prefix = prefix + '/'
            
            self.logger.debug(f"Using normalized prefix: '{prefix}'")
            
            while True:
                self.logger.debug(f"Fetching page with marker: {continuation_token}")
                result = self._list_objects_page(prefix, delimiter, continuation_token)
                
                # 添加文件
                all_objects.extend(result['objects'])
                total_files += len(result['objects'])
                
                # 如果不是递归模式，添加文件夹
                if not recursive:
                    for prefix_path in result['common_prefixes']:
                        # 从完整前缀路径中提取文件夹名称
                        folder_name = prefix_path
                        if prefix and folder_name.startswith(prefix):
                            # 只显示当前层级的文件夹名称
                            folder_name = folder_name[len(prefix):]
                            if folder_name.endswith('/'):
                                folder_name = folder_name[:-1]
                        
                        self.logger.debug(f"Adding folder: {folder_name} (full path: {prefix_path})")
                        
                        all_objects.append({
                            'name': prefix_path,  # 保存完整路径
                            'display_name': folder_name,  # 显示名称
                            'size': 0,
                            'last_modified': None,
                            'type': 'folder'
                        })
                        total_folders += 1
                
                self.logger.debug(f"Retrieved {len(result['objects'])} files and {len(result['common_prefixes'])} folders in this page")
                
                # 检查是否还有更多页
                continuation_token = result.get('next_token')
                if not continuation_token:
                    break
                    
            self.logger.info(f"Successfully listed {total_files} files and {total_folders} folders for prefix '{prefix}'")
            return all_objects
            
        except Exception as e:
            self.logger.error(f"Failed to list objects: {str(e)}")
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
            
            # 使用阿里云 SDK 的 put_object 方法
            self.bucket.put_object(
                object_name,
                data,
                headers={'Content-Type': content_type} if content_type else None
            )
            
            self.logger.debug(f"Put object completed: {object_name}")
            return self.get_public_url(object_name)
            
        except OssError as e:
            self.logger.error(f"Put object failed: {str(e)}")
            raise UploadError(f"Upload failed: {str(e)}")

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
            
            # 使用 oss2 的 get_object 方法获取对象
            response = self.bucket.get_object(object_name)
            
            # 读取所有内容
            content = response.read()
            
            # 关闭响应
            response.close()
            
            return content
            
        except oss2.exceptions.NoSuchKey:
            raise ObjectNotFoundError(f"Object not found: {object_name}")
            
        except Exception as e:
            self.logger.error(f"Failed to get object {object_name}: {str(e)}")
            raise OSSError(f"Failed to get object: {str(e)}")

    def _list_objects_page(self, prefix: str = '', delimiter: str = '/', continuation_token: str = None) -> dict:
        """获取一页对象列表"""
        try:
            self.logger.debug(f"Listing objects page with prefix='{prefix}', delimiter='{delimiter}', marker='{continuation_token}'")
            
            # 构建请求参数
            params = {
                'prefix': prefix,
                'delimiter': delimiter,
                'max_keys': 1000
            }
            
            if continuation_token:
                params['marker'] = continuation_token
            
            # 获取一页数据
            result = self.bucket.list_objects(**params)
            
            self.logger.debug(f"Raw response - is_truncated: {result.is_truncated}, next_marker: {result.next_marker}")
            
            # 处理文件夹（CommonPrefixes）
            common_prefixes = []
            if hasattr(result, 'prefix_list'):
                for prefix_info in result.prefix_list:
                    # 确保我们获取正确的前缀值
                    if hasattr(prefix_info, 'prefix'):
                        prefix_path = prefix_info.prefix
                    else:
                        prefix_path = prefix_info
                    self.logger.debug(f"Found common prefix (folder): {prefix_path}")
                    common_prefixes.append(prefix_path)
            
            # 处理文件
            objects = []
            for obj in result.object_list:
                # 跳过表示目录的对象
                if obj.key.endswith('/'):
                    self.logger.debug(f"Skipping directory marker: {obj.key}")
                    continue
                
                # 处理时间戳
                last_modified = obj.last_modified
                self.logger.debug(f"Processing object: {obj.key}, size: {obj.size}, last_modified: {last_modified}")
                
                objects.append({
                    'name': obj.key,
                    'size': obj.size,
                    'last_modified': last_modified,
                    'type': 'file'
                })
            
            response = {
                'objects': objects,
                'common_prefixes': common_prefixes,
                'next_token': result.next_marker if result.is_truncated else None
            }
            
            self.logger.debug(f"Page result - files: {len(objects)}, folders: {len(common_prefixes)}, has_more: {result.is_truncated}")
            return response
            
        except Exception as e:
            self.logger.error(f"Failed to list objects page: {str(e)}")
            raise OSSError(f"Failed to list objects page: {str(e)}")
