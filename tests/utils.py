import threading
import time
from colorama import Fore, Style

class SizeFormatter:
    @staticmethod
    def format_size(size_bytes: int) -> str:
        """格式化文件大小显示"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024:
                return f"{size_bytes:.1f}{unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f}TB"

class PartUploadProgress:
    """分片上传进度跟踪器"""
    def __init__(self, part_number: int, total_size: int):
        self.part_number = part_number
        self.total_size = total_size
        self.uploaded = 0
        self.start_time = time.time()
        self.last_update = time.time()
        self.status = 'pending'  # pending, uploading, completed, failed
        self.speed = 0
        self._lock = threading.Lock()

    def update(self, bytes_uploaded: int):
        with self._lock:
            self.uploaded += bytes_uploaded
            now = time.time()
            elapsed = now - self.last_update
            if elapsed > 0:
                self.speed = bytes_uploaded / elapsed
            self.last_update = now
            
            if self.uploaded >= self.total_size:
                self.status = 'completed'
            else:
                self.status = 'uploading'

    @property
    def progress(self) -> float:
        return (self.uploaded / self.total_size) * 100 if self.total_size > 0 else 0

    @property
    def is_stalled(self) -> bool:
        return time.time() - self.last_update > 5  # 5秒无更新视为stalled

class ConcurrentProgressTracker:
    """跟踪多个文件的并发上传进度"""
    def __init__(self, total_parts: int):
        self.lock = threading.Lock()
        self.progress_by_part = {}  # 每个分片的进度
        self.total_parts = total_parts
        self.completed_parts = 0
        self.start_time = time.time()
        self._last_line_count = 0
        
    def add_part(self, part_number: int, progress: PartUploadProgress):
        """添加新的分片进度"""
        with self.lock:
            self.progress_by_part[part_number] = progress
            self._print_progress()
    
    def update_part(self, part_number: int, bytes_transferred: int):
        """更新分片进度"""
        with self.lock:
            if part_number in self.progress_by_part:
                self.progress_by_part[part_number].update(bytes_transferred)
                self._print_progress()
    
    def part_completed(self, part_number: int):
        """标记分片完成"""
        with self.lock:
            if part_number in self.progress_by_part:
                self.completed_parts += 1
                self.progress_by_part[part_number].status = 'completed'
                self._print_progress()
    
    def part_failed(self, part_number: int, error: str):
        """标记分片失败"""
        with self.lock:
            if part_number in self.progress_by_part:
                self.progress_by_part[part_number].status = 'failed'
                self.progress_by_part[part_number].error = error
                self._print_progress()
    
    def _print_progress(self):
        """打印所有分片的进度"""
        # 清除之前的输出
        if self._last_line_count > 0:
            print('\033[F' * self._last_line_count + '\033[J', end='')
        
        lines = []
        lines.append(f"{Fore.CYAN}Upload Progress: {self.completed_parts}/{self.total_parts} parts{Style.RESET_ALL}")
        lines.append("=" * 70)
        
        for part_num, progress in sorted(self.progress_by_part.items()):
            # 确定状态和颜色
            if progress.status == 'completed':
                status_color = Fore.GREEN
            elif progress.status == 'failed':
                status_color = Fore.RED
            elif progress.is_stalled:
                status_color = Fore.RED
                progress.status = 'stalled'
            else:
                status_color = Fore.YELLOW
            
            # 格式化进度条
            bar_width = 20
            filled = int(bar_width * progress.progress / 100)
            progress_bar = '█' * filled + '░' * (bar_width - filled)
            
            # 计算速度
            speed_mb = progress.speed / (1024 * 1024)
            
            # 构建进度行
            lines.append(
                f"{status_color}Part {part_num:2d}: "
                f"{progress.progress:6.1f}% "
                f"[{progress_bar}] "
                f"({SizeFormatter.format_size(progress.uploaded)}/"
                f"{SizeFormatter.format_size(progress.total_size)}) "
                f"- {speed_mb:.1f} MB/s [{progress.status}]{Style.RESET_ALL}"
            )
        
        lines.append("=" * 70)
        print('\n'.join(lines))
        self._last_line_count = len(lines)

class CallbackIOWrapper:
    """用于跟踪IO进度的包装器"""
    def __init__(self, callback, stream, total_size: int):
        self._callback = callback
        self._stream = stream
        self._total_size = total_size
        self._bytes_read = 0

    def read(self, size: int = -1) -> bytes:
        """读取数据并调用回调"""
        chunk = self._stream.read(size)
        if chunk:
            self._bytes_read += len(chunk)
            if self._callback:
                self._callback(len(chunk))
        return chunk

    def seek(self, offset: int, whence: int = 0) -> int:
        """移动流位置"""
        return self._stream.seek(offset, whence)

    def tell(self) -> int:
        """获取当前位置"""
        return self._stream.tell() 