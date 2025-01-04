import tkinter as tk
from PIL import ImageGrab, Image
import win32clipboard
import io
import logging
from datetime import datetime
import os

class ClipboardHelper:
    """剪贴板处理工具类"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def get_clipboard_type(self):
        """获取剪贴板内容类型"""
        try:
            # 尝试获取文件列表
            files = self.get_file_paths()
            if files:
                return "files", files
            
            # 尝试获取图片
            image = self.get_image()
            if image:
                return "image", image
            
            return None, None
            
        except Exception as e:
            self.logger.error(f"Failed to get clipboard type: {str(e)}")
            return None, None
    
    def get_file_paths(self):
        """获取剪贴板中的文件路径列表"""
        try:
            win32clipboard.OpenClipboard()
            try:
                if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_HDROP):
                    from ctypes import windll
                    data = win32clipboard.GetClipboardData(win32clipboard.CF_HDROP)
                    return [data[i] for i in range(len(data))]
            finally:
                win32clipboard.CloseClipboard()
        except Exception as e:
            self.logger.error(f"Failed to get file paths: {str(e)}")
        return None
    
    def get_image(self):
        """获取剪贴板中的图片"""
        try:
            # 尝试直接获取图片
            image = ImageGrab.grabclipboard()
            if isinstance(image, Image.Image):
                return image
            
            # 尝试从 DIB 获取图片
            win32clipboard.OpenClipboard()
            try:
                if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_DIB):
                    data = win32clipboard.GetClipboardData(win32clipboard.CF_DIB)
                    stream = io.BytesIO(data)
                    image = Image.open(stream)
                    return image
            finally:
                win32clipboard.CloseClipboard()
                
        except Exception as e:
            self.logger.error(f"Failed to get image: {str(e)}")
        return None
    
    @staticmethod
    def generate_image_filename(prefix="clipboard", ext=".png"):
        """生成图片文件名"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{prefix}_{timestamp}{ext}" 