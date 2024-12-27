from typing import Optional, List, Tuple
from dataclasses import dataclass
from datetime import datetime

@dataclass
class OSSConfig:
    """OSS配置类"""
    endpoint: str
    access_key: str
    secret_key: str
    bucket_name: str
    secure: bool = True
    region: Optional[str] = None
    proxy: Optional[str] = None  # 添加代理配置

@dataclass
class TransferProgress:
    """传输进度类"""
    transferred: int = 0  # 已传输字节数
    total: int = 0  # 总字节数
    start_time: datetime = None  # 开始时间
    speed: float = 0  # 传输速度 (bytes/s)
    percentage: float = 0  # 完成百分比
    
    def __post_init__(self):
        self.start_time = datetime.now()
    
    def update(self, increment: int):
        """更新进度"""
        self.transferred += increment
        elapsed = (datetime.now() - self.start_time).total_seconds()
        self.speed = self.transferred / elapsed if elapsed > 0 else 0
        self.percentage = (self.transferred / self.total) * 100 if self.total > 0 else 0

class ProgressCallback:
    """进度回调类"""
    def __init__(self, total_size: int):
        self.progress = TransferProgress(total=total_size)
    
    def __call__(self, bytes_amount):
        self.progress.update(bytes_amount)
        self.on_progress(
            self.progress.transferred,
            self.progress.total,
            self.progress.speed
        )
    
    def on_progress(self, transferred: int, total: int, speed: float):
        """进度回调方法，可被覆盖"""
        percentage = (transferred / total) * 100
        print(f"Progress: {percentage:.1f}% ({transferred}/{total} bytes) - {speed:.1f} bytes/s")

@dataclass
class MultipartUpload:
    """分片上传信息"""
    def __init__(self, object_name: str, upload_id: str):
        self.object_name = object_name
        self.upload_id = upload_id
        self.parts = []  # List of (part_number, etag)
        self.part_size = 5 * 1024 * 1024  # 默认 5MB 分片大小