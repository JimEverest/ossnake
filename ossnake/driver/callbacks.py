from datetime import datetime
from .types import ProgressCallback

class ConsoleProgressCallback(ProgressCallback):
    """控制台进度显示"""
    def __init__(self, update_interval: float = 0.5):
        self.update_interval = update_interval
        self.last_update = datetime.now()
        
    def on_progress(
        self,
        bytes_transferred: int,
        total_bytes: int,
        start_time: datetime,
        current_speed: float
    ) -> None:
        now = datetime.now()
        if (now - self.last_update).total_seconds() >= self.update_interval:
            percentage = (bytes_transferred / total_bytes) * 100
            elapsed = (now - start_time).total_seconds()
            speed_mb = current_speed / (1024 * 1024)
            
            print(f"\rProgress: {percentage:.1f}% "
                  f"({bytes_transferred}/{total_bytes} bytes) "
                  f"Speed: {speed_mb:.2f} MB/s "
                  f"Elapsed: {elapsed:.1f}s", end="")
            
            self.last_update = now

class FileProgressCallback(ProgressCallback):
    """文件进度记录"""
    def __init__(self, log_file: str):
        self.log_file = log_file
        
    def on_progress(
        self,
        bytes_transferred: int,
        total_bytes: int,
        start_time: datetime,
        current_speed: float
    ) -> None:
        with open(self.log_file, 'a') as f:
            percentage = (bytes_transferred / total_bytes) * 100
            elapsed = (datetime.now() - start_time).total_seconds()
            speed_mb = current_speed / (1024 * 1024)
            
            f.write(f"{datetime.now()}: "
                   f"Progress: {percentage:.1f}% "
                   f"({bytes_transferred}/{total_bytes} bytes) "
                   f"Speed: {speed_mb:.2f} MB/s "
                   f"Elapsed: {elapsed:.1f}s\n") 