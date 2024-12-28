import os
import logging
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from typing import Optional, Callable

class TransferManager:
    """传输管理器，处理分片上传下载"""
    
    def __init__(self, 
                 chunk_size: int = 5 * 1024 * 1024,  # 5MB
                 max_workers: int = 4):
        self.chunk_size = chunk_size
        self.max_workers = max_workers
        self.logger = logging.getLogger(__name__)
        self._lock = Lock()
        
    def upload_file(self, 
                    client, 
                    local_file: str, 
                    remote_path: str,
                    progress_callback: Optional[Callable] = None) -> str:
        """分片上传文件"""
        try:
            file_size = os.path.getsize(local_file)
            transferred = 0  # 已传输字节数
            
            def update_progress(chunk_size, *args):  # 添加 *args 来处理额外参数
                """进度回调包装器，处理不同客户端的回调格式"""
                nonlocal transferred
                # 如果传入的是元组，取第一个值
                if isinstance(chunk_size, tuple):
                    chunk_size = chunk_size[0]
                transferred += chunk_size
                if progress_callback:
                    progress_callback(transferred, file_size)
            
            # 小文件直接上传
            if file_size <= self.chunk_size:
                if progress_callback:
                    progress_callback(0, file_size)  # 初始进度
                result = client.upload_file(local_file, remote_path, update_progress)
                if progress_callback:
                    progress_callback(file_size, file_size)  # 完成进度
                return result
            
            # 初始化分片上传
            upload = client.init_multipart_upload(remote_path)
            self.logger.info(f"Started multipart upload: {upload.upload_id}")
            
            # 计算分片数量
            total_parts = (file_size + self.chunk_size - 1) // self.chunk_size
            
            # 先只实现单线程上传，确保基本功能正常
            with open(local_file, 'rb') as f:
                part_number = 1
                
                while True:
                    chunk = f.read(self.chunk_size)
                    if not chunk:
                        break
                    
                    # 上传分片
                    etag = client.upload_part(upload, part_number, chunk)
                    upload.parts.append((part_number, etag))
                    
                    # 更新进度
                    update_progress(len(chunk))
                    
                    part_number += 1
            
            # 完成上传
            return client.complete_multipart_upload(upload)
            
        except Exception as e:
            self.logger.error(f"Upload failed: {str(e)}")
            if 'upload' in locals():
                try:
                    client.abort_multipart_upload(upload)
                except:
                    pass
            raise 