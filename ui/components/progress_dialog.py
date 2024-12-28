import tkinter as tk
from tkinter import ttk
import threading
import time

class ProgressDialog(tk.Toplevel):
    def __init__(self, parent, title="进度", message="正在处理..."):
        super().__init__(parent)
        self.title(title)
        self.geometry("400x180")
        self.resizable(False, False)
        
        # 设置模态
        self.transient(parent)
        self.grab_set()
        
        # 主框架
        self.main_frame = ttk.Frame(self)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # 消息标签
        self.message_label = ttk.Label(self.main_frame, text=message)
        self.message_label.pack(fill=tk.X, pady=(0, 10))
        
        # 进度条框架
        self.progress_frame = ttk.Frame(self.main_frame)
        self.progress_frame.pack(fill=tk.X, pady=5)
        
        # 进度条
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(
            self.progress_frame,
            variable=self.progress_var,
            maximum=100,
            mode='determinate'
        )
        self.progress_bar.pack(fill=tk.X)
        
        # 详细信息框架
        self.detail_frame = ttk.Frame(self.main_frame)
        self.detail_frame.pack(fill=tk.X, pady=5)
        
        # 文件信息
        self.file_var = tk.StringVar()
        self.file_label = ttk.Label(
            self.detail_frame,
            textvariable=self.file_var,
            font=('TkDefaultFont', 9)
        )
        self.file_label.pack(anchor='w')
        
        # 速度信息
        self.speed_var = tk.StringVar()
        self.speed_label = ttk.Label(
            self.detail_frame,
            textvariable=self.speed_var,
            font=('TkDefaultFont', 9)
        )
        self.speed_label.pack(anchor='w')
        
        # 底部框架（用于取消按钮）
        self.button_frame = ttk.Frame(self.main_frame)
        self.button_frame.pack(fill=tk.X, pady=(10, 0))
        
        # 取消按钮
        self.cancel_button = ttk.Button(
            self.button_frame,
            text="取消",
            command=self.cancel,
            width=15
        )
        self.cancel_button.pack(side=tk.RIGHT)
        
        # 取消标志
        self.cancelled = False
        
        # 记录开始时间和已传输大小
        self.start_time = None
        self.transferred = 0
        
        # 居中显示
        self.center_window()
        
        # 设置最小尺寸
        self.minsize(400, 180)
    
    def center_window(self):
        """将窗口居中显示"""
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'{width}x{height}+{x}+{y}')
    
    def update_progress(self, percentage, current_file=None, transferred=None, total=None):
        """更新进度"""
        self.progress_var.set(percentage)
        
        if current_file:
            self.file_var.set(f"当前文件: {current_file}")
        
        if transferred is not None and total is not None:
            if self.start_time is None:
                self.start_time = time.time()
                self.transferred = 0
            
            elapsed = time.time() - self.start_time
            if elapsed > 0:
                speed = transferred / elapsed
                self.speed_var.set(f"速度: {self.format_speed(speed)} ({self.format_size(transferred)}/{self.format_size(total)})")
        
        self.update_idletasks()
    
    @staticmethod
    def format_size(size):
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"
    
    @staticmethod
    def format_speed(speed):
        """格式化速度"""
        return f"{ProgressDialog.format_size(speed)}/s"
    
    def cancel(self):
        """取消操作"""
        self.cancelled = True
        self.cancel_button.config(state='disabled')
        self.file_var.set("正在取消...")
        self.speed_var.set("")
        self.progress_bar.config(mode='indeterminate')
        self.progress_bar.start(10)  # 开始动画 