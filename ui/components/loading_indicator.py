import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import os

class LoadingIndicator(ttk.Label):
    """加载指示器组件"""
    
    def __init__(self, parent, size=64):
        super().__init__(parent)
        self.size = size
        self.frames = []
        self.current_frame = 0
        
        # 设置背景和边框
        self.configure(
            background='white',
            relief='solid',
            borderwidth=1,
            padding=10
        )
        
        # 加载GIF文件
        gif_path = os.path.join('assets', 'loading.gif')
        if os.path.exists(gif_path):
            # 加载GIF动画
            gif = Image.open(gif_path)
            
            # 获取所有帧
            try:
                while True:
                    # 调整大小并转换为PhotoImage
                    frame = gif.copy()
                    frame = frame.resize((size, size), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(frame)
                    self.frames.append(photo)
                    gif.seek(len(self.frames))
            except EOFError:
                pass
            
            # 如果成功加载了帧
            if self.frames:
                self.configure(image=self.frames[0])
                self.start_animation()
    
    def start_animation(self):
        """开始动画"""
        if not self.frames:
            return
            
        def update():
            if not self.winfo_exists():
                return
                
            self.current_frame = (self.current_frame + 1) % len(self.frames)
            self.configure(image=self.frames[self.current_frame])
            self.after(100, update)  # 每100ms更新一次
        
        update() 