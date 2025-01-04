# ui/file_preview.py
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import requests
import io
import json
import vlc  # 需要安装 python-vlc
from tkinter.scrolledtext import ScrolledText

class FilePreviewWindow(tk.Toplevel):
    def __init__(self, parent, url):
        super().__init__(parent)
        self.title("文件预览")
        self.geometry("800x600")
        self.url = url
        self.create_widgets()
        self.load_content()
    
    def create_widgets(self):
        self.content_frame = ttk.Frame(self)
        self.content_frame.pack(expand=True, fill=tk.BOTH)
    
    def load_content(self):
        # 通过HEAD请求获取Content-Type
        response = requests.head(self.url)
        content_type = response.headers.get('Content-Type', '')
        
        if 'image' in content_type:
            self.preview_image()
        elif 'text' in content_type or 'json' in content_type:
            self.preview_text()
        elif 'audio' in content_type:
            self.preview_audio()
        elif 'video' in content_type:
            self.preview_video()
        else:
            ttk.Label(self.content_frame, text="无法预览此文件类型").pack()
    
    def preview_image(self):
        response = requests.get(self.url)
        image_data = response.content
        image = Image.open(io.BytesIO(image_data))
        photo = ImageTk.PhotoImage(image)
        label = ttk.Label(self.content_frame, image=photo)
        label.image = photo  # 保持引用
        label.pack(expand=True)
    
    def preview_text(self):
        response = requests.get(self.url)
        text = response.text
        text_widget = ScrolledText(self.content_frame)
        text_widget.insert(tk.END, text)
        text_widget.configure(state='disabled')
        text_widget.pack(expand=True, fill=tk.BOTH)
    
    def preview_audio(self):
        # 使用 VLC 播放音频
        player = vlc.MediaPlayer(self.url)
        player.play()
        ttk.Label(self.content_frame, text="正在播放音频...").pack()
    
    def preview_video(self):
        # VLC 可以嵌入视频到Tkinter窗口
        # 这里提供简单的播放控制
        # 注意: 预览音视频需要安装python-vlc和系统中安装VLC播放器。可以通过pip install python-vlc安装Python绑定。
        player = vlc.MediaPlayer(self.url)
        player.play()
        ttk.Label(self.content_frame, text="正在播放视频...").pack()



    def preview_image(self):
        response = requests.get(self.url)
        image_data = response.content
        image = Image.open(io.BytesIO(image_data))
        
        self.image = ImageTk.PhotoImage(image)
        self.label = ttk.Label(self.content_frame, image=self.image)
        self.label.pack(expand=True)
        
        # 添加缩放功能
        self.label.bind("<MouseWheel>", self.zoom_image)
        self.scale = 1.0
    
    def zoom_image(self, event):
        if event.delta > 0:
            self.scale *= 1.1
        else:
            self.scale /= 1.1
        resized = self.image._PhotoImage__photo.zoom(int(self.scale * 10))  # 简单缩放
        self.label.config(image=resized)
        self.label.image = resized