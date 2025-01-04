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
            
            # 小文件直接上传
            if file_size <= self.chunk_size:
                if progress_callback:
                    progress_callback(0, file_size)  # 初始进度
                    
                    # 创建小文件上传的进度回调包装器
                    def small_file_callback(chunk_size):
                        nonlocal transferred
                        transferred += chunk_size
                        progress_callback(transferred, file_size)
                        
                    result = client.upload_file(local_file, remote_path, small_file_callback)
                else:
                    result = client.upload_file(local_file, remote_path, None)
                    
                if progress_callback:
                    progress_callback(file_size, file_size)  # 完成进度
                return result
            
            # 初始化分片上传
            upload = client.init_multipart_upload(remote_path)
            self.logger.info(f"Started multipart upload: {upload.upload_id}")
            
            # 计算分片数量和每个分片的大小
            total_parts = (file_size + self.chunk_size - 1) // self.chunk_size
            self.logger.info(f"Total parts: {total_parts}, File size: {file_size}, Chunk size: {self.chunk_size}")
            
            # 创建分片进度跟踪
            part_progress = {i: 0 for i in range(1, total_parts + 1)}
            
            def update_progress(part_number: int, chunk_size: int):
                """更新分片和总体进度"""
                nonlocal transferred
                with self._lock:
                    transferred += chunk_size
                    part_progress[part_number] += chunk_size
                    if progress_callback:
                        # 计算当前分片的总大小
                        if part_number == total_parts:
                            # 最后一个分片的大小可能不足chunk_size
                            part_total = file_size - (total_parts - 1) * self.chunk_size
                        else:
                            part_total = self.chunk_size
                            
                        progress_callback(
                            transferred,  # 总已传输
                            file_size,    # 总大小
                            part_number,  # 分片号
                            part_progress[part_number],  # 分片已传输
                            part_total    # 分片大小
                        )
            
            # 创建任务列表
            tasks = []
            with open(local_file, 'rb') as f:
                for part_number in range(1, total_parts + 1):
                    # 计算当前分片大小
                    chunk_start = (part_number - 1) * self.chunk_size
                    f.seek(chunk_start)
                    
                    # 对于最后一个分片，只读取剩余的字节
                    if part_number == total_parts:
                        chunk_size = file_size - chunk_start
                    else:
                        chunk_size = self.chunk_size
                        
                    chunk = f.read(chunk_size)
                    tasks.append((part_number, chunk))
                    
                    self.logger.debug(f"Created task for part {part_number}, size: {len(chunk)}")
            
            # 使用线程池并发上传分片
            completed_parts = []
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                def upload_part(args):
                    part_number, data = args
                    try:
                        etag = client.upload_part(upload, part_number, data)
                        update_progress(part_number, len(data))
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