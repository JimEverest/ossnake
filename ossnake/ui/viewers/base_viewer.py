import tkinter as tk
from tkinter import messagebox

class BaseViewer(tk.Toplevel):
    """基础查看器类"""
    
    def __init__(self, parent):
        super().__init__(parent)
        self.geometry("800x600")
        self.minsize(400, 300)
        
        # 使窗口模态
        self.transient(parent)
        self.grab_set()
    
    def show_error(self, title: str, message: str):
        """显示错误消息"""
        messagebox.showerror(title, message) 