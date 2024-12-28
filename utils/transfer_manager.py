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
            
            def update_progress(chunk_size, *args):
                """进度回调包装器，处理不同客户端的回调格式"""
                nonlocal transferred
                with self._lock:
                    if isinstance(chunk_size, tuple):
                        chunk_size = chunk_size[0]
                    transferred += int(chunk_size)
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
            
            # 计算分片数量和大小
            total_parts = (file_size + self.chunk_size - 1) // self.chunk_size
            
            # 创建任务列表
            tasks = []
            with open(local_file, 'rb') as f:
                for part_number in range(1, total_parts + 1):
                    # 计算当前分片大小
                    chunk_start = (part_number - 1) * self.chunk_size
                    f.seek(chunk_start)
                    chunk = f.read(self.chunk_size)
                    
                    # 添加到任务列表
                    tasks.append((part_number, chunk))
            
            # 使用线程池并发上传分片
            completed_parts = []
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                def upload_part(args):
                    part_number, data = args
                    try:
                        etag = client.upload_part(upload, part_number, data)
                        update_progress(len(data))
                        return part_number, etag
                    except Exception as e:
                        self.logger.error(f"Failed to upload part {part_number}: {e}")
                        raise
                
                # 提交所有任务并等待完成
                futures = [executor.submit(upload_part, task) for task in tasks]
                for future in futures:
                    part_number, etag = future.result()
                    completed_parts.append((part_number, etag))
            
            # 按分片号排序
            upload.parts = sorted(completed_parts, key=lambda x: x[0])
            
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