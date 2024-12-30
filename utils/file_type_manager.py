from typing import Dict, Type
from enum import Enum
import logging

class FileAction(Enum):
    """文件操作类型"""
    VIEW = "view"      # 只读预览
    EDIT = "edit"      # 可以编辑
    BOTH = "both"      # 既可以预览也可以编辑

class FileTypeManager:
    """文件类型管理器"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        # 文件类型映射表
        self._viewers = {}
        self._editors = {}
        self._extensions = {}
        
        # 初始化基本映射
        self._init_mappings()
    
    def _init_mappings(self):
        """初始化基本的文件类型映射"""
        from ui.viewers.text_editor import TextEditor
        from ui.viewers.image_viewer import ImageViewer
        
        # 注册文本编辑器
        self.register_handler(
            extensions=['.txt', '.py', '.md'],
            handler=TextEditor,
            action=FileAction.BOTH
        )
        
        # 注册图片查看器
        self.register_handler(
            extensions=['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'],
            handler=ImageViewer,
            action=FileAction.VIEW
        )
    
    def register_handler(self, extensions: list, handler: Type, action: FileAction):
        """注册文件处理器"""
        try:
            for ext in extensions:
                ext = ext.lower()
                self._extensions[ext] = {
                    'handler': handler,
                    'action': action
                }
            self.logger.info(f"Registered {handler.__name__} for extensions: {extensions}")
        except Exception as e:
            self.logger.error(f"Failed to register handler: {str(e)}")
    
    def get_handler(self, filename: str) -> tuple:
        """获取文件处理器
        Returns:
            tuple: (handler_class, action) 或 (None, None)
        """
        ext = self._get_extension(filename)
        if ext in self._extensions:
            return (
                self._extensions[ext]['handler'],
                self._extensions[ext]['action']
            )
        return None, None
    
    @staticmethod
    def _get_extension(filename: str) -> str:
        """获取文件扩展名"""
        import os
        ext = os.path.splitext(filename)[1].lower()
        return ext if ext else '' 