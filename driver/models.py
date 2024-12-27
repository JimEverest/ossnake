from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

@dataclass
class OSSConfig:
    endpoint: str
    access_key: str
    secret_key: str
    bucket_name: str
    region: Optional[str] = None
    secure: bool = True
    proxy: Optional[Dict[str, str]] = None

@dataclass
class TransferProgress:
    """传输进度信息"""
    total_size: int
    transferred: int
    parts_completed: Dict[int, bool]  # 分片完成状态
    start_time: datetime
    last_update: datetime
    checksum: str  # 文件校验和
    temp_file: str  # 临时文件路径
    
    @property
    def progress_percentage(self) -> float:
        """获取进度百分比"""
        return (self.transferred / self.total_size * 100) if self.total_size > 0 else 0

class MultipartUpload:
    """分片上传信息"""
    def __init__(self, upload_id: str, object_name: str, total_parts: int):
        self.upload_id = upload_id
        self.object_name = object_name
        self.total_parts = total_parts
        self.parts: List[Tuple[int, str]] = []  # [(part_number, etag), ...] 