import tkinter as tk
from tkinter import ttk
import threading
import time
import logging

class ProgressDialog(tk.Toplevel):
    def __init__(self, parent, title="进度", message="正在处理...", multipart=False, total_parts=0):
        super().__init__(parent)
        self.title(title)
        
        # 根据分片数量动态计算窗口高度
        base_height = 180  # 基础高度
        part_height = 35   # 每个分片进度条的高度
        padding = 20       # 额外padding
        
        if multipart and total_parts > 0:
            window_height = base_height + (part_height * total_parts) + padding
        else:
            window_height = base_height
            
        self.geometry(f"400x{window_height}")
        self.resizable(False, False)
        
        # 设置模态
        self.transient(parent)
        self.grab_set()
        
        # 创建主滚动框架
        self.canvas = tk.Canvas(self)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        # 主框架
        self.main_frame = ttk.Frame(self.scrollable_frame)
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
        
        # 添加时间追踪变量
        self.last_update_time = None
        self.last_transferred = 0
        self.logger = logging.getLogger(__name__)
        
        # 居中显示
        self.center_window()
        
        # 设置最小尺寸
        self.minsize(400, 180)
        
        # 如果是分片上传，添加分片进度显示
        if multipart and total_parts > 0:
            # 分片进度框架
            self.parts_frame = ttk.LabelFrame(self.main_frame, text="分片进度")
            self.parts_frame.pack(fill=tk.BOTH, expand=True, pady=5)
            
            # 创建分片进度条
            self.part_progresses = {}
            self.part_labels = {}
            for i in range(1, total_parts + 1):
                frame = ttk.Frame(self.parts_frame)
                frame.pack(fill=tk.X, padx=5, pady=2)
                
                label = ttk.Label(frame, text=f"分片 {i}", width=10)
                label.pack(side=tk.LEFT)
                
                progress = ttk.Progressbar(frame, mode='determinate')
                progress.pack(side=tk.LEFT, fill=tk.X, expand=True)
                
                self.part_progresses[i] = progress
                self.part_labels[i] = label
        
        # 布局滚动区域
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        
        # 绑定鼠标滚轮
        self.bind_all("<MouseWheel>", self._on_mousewheel)
        
    def center_window(self):
        """将窗口居中显示"""
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'{width}x{height}+{x}+{y}')
    
    def update_progress(self, transferred, total, current_file=None, *args):
        """更新进度
        Args:
            transferred: 已传输字节数
            total: 总字节数
            current_file: 当前文件名（可选）
            *args: 其他参数（向后兼容）
        """
        try:
            if total > 0:
                # 确保使用整数计算避免精度问题
                transferred = int(transferred)
                total = int(total)
                
                # 计算百分比
                percentage = min(100, (transferred * 100) / total)
                self.progress_var.set(percentage)
                
                # 更新文件信息
                if current_file:
                    self.file_var.set(f"当前文件: {current_file}")
                else:
                    self.file_var.set(f"已传输: {self.format_size(transferred)} / {self.format_size(total)}")
                
                # 计算速度
                current_time = time.time()
                if self.start_time is None:
                    self.start_time = current_time
                    self.last_update_time = current_time
                    self.last_transferred = 0
                else:
                    # 计算这一段时间的速度
                    time_diff = current_time - self.last_update_time
                    if time_diff >= 0.5:  # 每0.5秒更新一次速度
                        bytes_diff = transferred - self.last_transferred
                        speed = bytes_diff / time_diff
                        self.speed_var.set(f"速度: {self.format_speed(speed)}")
                        
                        # 更新上次的值
                        self.last_update_time = current_time
                        self.last_transferred = transferred
            
            self.update_idletasks()
            
        except Exception as e:
            self.logger.error(f"Error updating progress: {str(e)}")
    
    @staticmethod
    def format_size(size: int) -> str:
        """格式化文件大小"""
        try:
            size = int(size)  # 确保是整数
            for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
                if size < 1024:
                    return f"{size:.1f} {unit}"
                size /= 1024.0  # 使用浮点数除法
            return f"{size:.1f} PB"
        except Exception:
            return "0 B"
    
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
    
    def close(self):
        """关闭对话框"""
        self.destroy()  # 使用 destroy 替代 close
    
    def destroy(self):
        """重写 destroy 方法，确保清理"""
        if hasattr(self, 'progress_bar') and self.progress_bar:
            self.progress_bar.stop()  # 停止进度条动画
        super().destroy() 
    
    def update_part_progress(self, part_number: int, transferred: int, total: int):
        """更新分片进度"""
        if hasattr(self, 'part_progresses') and part_number in self.part_progresses:
            percentage = min(100, (transferred * 100) / total)
            self.part_progresses[part_number]['value'] = percentage
            self.part_labels[part_number].config(
                text=f"分片 {part_number}: {percentage:.1f}%"
            )
            self.update_idletasks() 
    
    def _on_mousewheel(self, event):
        """处理鼠标滚轮事件"""
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units") 