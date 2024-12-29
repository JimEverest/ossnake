import tkinter as tk
from tkinter import ttk
import threading
import time

class Toast(tk.Toplevel):
    """Toast 通知组件"""
    
    def __init__(self, parent, message, duration=2000):
        """
        Args:
            parent: 父窗口
            message: 显示消息
            duration: 显示时长(毫秒)
        """
        super().__init__(parent)
        
        # 设置窗口属性
        self.overrideredirect(True)  # 无边框
        self.attributes('-topmost', True)  # 置顶
        
        # 创建标签
        self.label = ttk.Label(
            self,
            text=message,
            padding=(20, 10),
            background='#2d2d2d',
            foreground='white'
        )
        self.label.pack()
        
        # 设置样式
        self.configure(background='#2d2d2d')
        
        # 计算位置
        self.update_idletasks()
        parent_x = parent.winfo_x()
        parent_y = parent.winfo_y()
        parent_width = parent.winfo_width()
        parent_height = parent.winfo_height()
        
        width = self.winfo_width()
        height = self.winfo_height()
        
        x = parent_x + (parent_width - width) // 2
        y = parent_y + parent_height - height - 50  # 距底部50像素
        
        self.geometry(f'+{x}+{y}')
        
        # 启动自动关闭线程
        threading.Thread(target=self._auto_close, args=(duration,), daemon=True).start()
    
    def _auto_close(self, duration):
        """自动关闭"""
        time.sleep(duration / 1000)  # 转换为秒
        self.destroy() 