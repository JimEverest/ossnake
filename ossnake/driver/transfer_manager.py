from typing import Optional, Dict, BinaryIO, Callable, Tuple
import os
import json
import hashlib
from datetime import datetime
import threading
from concurrent.futures import ThreadPoolExecutor
import logging
from io import BytesIO
import time

from .types import MultipartUpload, ProgressCallback, TransferProgress
from .exceptions import TransferError

class TransferMetrics:
    """传输指标收集"""
    def __init__(self):
        self.start_time = datetime.now()
        self.metrics = {
            'retries': 0,
            'failed_parts': 0,
            'network_errors': 0,
            'average_speed': 0
        }
        
    def record_retry(self):
        self.metrics['retries'] += 1
        
    def get_report(self):
        return {
            'duration': (datetime.now() - self.start_time).total_seconds(),
            **self.metrics
        }

class TransferManager:
    """
    断点续传管理器
    
    功能：
    1. 文件分片管理
    2. 进度保存和恢复
    3. 并发传输控制
    4. 校验和验证
    5. 传输速度控制
    6. 错误重试
    """
    
    CHUNK_SIZE = 5 * 1024 * 1024  # 5MB分片大小
    MAX_WORKERS = 4  # 并发数
    MAX_RETRIES = 3  # 最大重试次数
    
    def __init__(self):
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger("TransferManager")
        self.lock = threading.Lock()
        self.start_time = datetime.now()
        self.last_bytes = 0
        self.last_time = self.start_time

    def _calculate_speed(self, current_bytes: int) -> float:
        """计算当前传输速度"""
        now = datetime.now()
        elapsed = (now - self.last_time).total_seconds()
        if elapsed > 0:
            speed = (current_bytes - self.last_bytes) / elapsed
            self.last_bytes = current_bytes
            self.last_time = now
            return speed
        return 0

    def upload_file(
        self,
        client: 'BaseOSSClient',
        local_file: str,
        object_name: str,
        progress_callback: Optional[ProgressCallback] = None
    ) -> str:
        """上传文件（使用分片上传）"""
        try:
            if not os.path.exists(local_file):
                raise FileNotFoundError(f"Local file not found: {local_file}")
            
            # 初始化上传信息
            file_size = os.path.getsize(local_file)
            total_parts = (file_size + self.CHUNK_SIZE - 1) // self.CHUNK_SIZE
            
            self.logger.info(f"Starting multipart upload of {local_file} ({total_parts} parts)")
            
            # 初始化分片上传
            upload = client.init_multipart_upload(object_name)
            upload.total_parts = total_parts
            upload.total_size = file_size
            
            completed_parts = []
            try:
                # 并发上传分片
                with ThreadPoolExecutor(max_workers=self.MAX_WORKERS) as executor:
                    futures = []
                    for part_number in range(1, total_parts + 1):
                        future = executor.submit(
                            self._upload_part,
                            client,
                            local_file,
                            upload,
                            part_number,
                            progress_callback
                        )
                        futures.append(future)
                    
                    # 等待所有分片完成
                    for future in futures:
                        try:
                            part_info = future.result()
                            completed_parts.append(part_info)
                        except Exception as e:
                            # 取消所有未完成的任务
                            for f in futures:
                                f.cancel()
                            client.abort_multipart_upload(upload)
                            if isinstance(e, TransferError):
                                raise
                            raise TransferError(f"Upload failed: {str(e)}")
                
                # 完成上传
                upload.parts = sorted(completed_parts, key=lambda x: x[0])
                self.logger.info("All parts uploaded, completing multipart upload...")
                url = client.complete_multipart_upload(upload)
                self.logger.info("Upload completed successfully")
                return url
                
            except Exception as e:
                self.logger.error(f"Upload failed: {e}")
                try:
                    client.abort_multipart_upload(upload)
                except Exception as abort_error:
                    self.logger.warning(f"Failed to abort multipart upload: {abort_error}")
                raise
                
        except Exception as e:
            self.logger.error(f"Upload failed: {e}")
            raise

    def _upload_part(
        self,
        client: 'BaseOSSClient',
        local_file: str,
        upload: MultipartUpload,
        part_number: int,
        progress_callback: Optional[ProgressCallback] = None
    ) -> Tuple[int, str]:
        """上传单个分片"""
        try:
            # 计算分片范围
            start_pos = (part_number - 1) * self.CHUNK_SIZE
            with open(local_file, 'rb') as f:
                f.seek(start_pos)
                data = f.read(self.CHUNK_SIZE)
            
            # 上传分片
            etag = client.upload_part(upload, part_number, data)
            self.logger.info(f"Part {part_number} uploaded successfully")
            
            # 更新进度
            if progress_callback:
                try:
                    progress = upload.add_completed_part(part_number, etag, len(data))
                    progress_callback.on_progress(
                        upload.completed_bytes,
                        upload.total_size,
                        self.start_time,
                        self._calculate_speed(upload.completed_bytes)
                    )
                except Exception as e:
                    if isinstance(e, TransferError):
                        raise
                    self.logger.warning(f"Progress callback failed: {e}")
            
            return (part_number, etag)
            
        except Exception as e:
            if isinstance(e, TransferError):
                raise
            self.logger.warning(f"Part {part_number} upload failed: {e}")
            raise

    def get_progress(self, local_file: str, object_name: str) -> Optional[TransferProgress]:
        """获取传输进度"""
        transfer_key = self._get_transfer_key(local_file, object_name)
        return self.transfers.get(transfer_key) 

    def _update_progress(self, upload: MultipartUpload, completed_parts: list, 
                        progress_callback: ProgressCallback):
        """更新上传进度"""
        with self.lock:
            try:
                # 确保所有分片都完成
                if len(completed_parts) == upload.total_parts:
                    # 验证总大小
                    total_uploaded = sum(len(part[1]) for part in completed_parts)
                    if total_uploaded != upload.total_size:
                        raise ValueError(f"Size mismatch: {total_uploaded} != {upload.total_size}")
                
                # 调用回调
                progress_callback.on_progress(
                    upload.completed_bytes,
                    upload.total_size,
                    self.start_time,
                    self._calculate_speed(upload.completed_bytes)
                )
            except Exception as e:
                self.logger.warning(f"Progress callback failed: {e}")
                raise

    def _track_concurrent_progress(self, futures, callback):
        """追踪并发上传进度"""
        completed = set()
        for future in futures:
            try:
                result = future.result()
                completed.add(id(future))
                if callback:
                    callback.on_complete(len(completed))
            except Exception as e:
                self.logger.error(f"Upload failed: {e}")
                raise

    def _retry_operation(self, operation, max_retries=3):
        """统一的重试机制"""
        for retry in range(max_retries):
            try:
                return operation()
            except Exception as e:
                if retry == max_retries - 1:
                    raise
                self.logger.warning(f"Retry {retry + 1}/{max_retries}: {str(e)}")
                time.sleep(2 ** retry)  # 指数退避

    def _validate_progress(self, current: float, last: float):
        """验证进度的有效性"""
        if not (0 <= current <= 100):
            raise ValueError(f"Invalid progress value: {current}")
        if current < last and abs(current - last) > 0.1:  # 允许小误差
            raise ValueError(f"Progress decreased: {current} < {last}")