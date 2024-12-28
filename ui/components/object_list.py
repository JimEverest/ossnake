import tkinter as tk
from tkinter import ttk
import logging
from tkinter import messagebox
from PIL import Image, ImageTk
import os
import base64
from io import BytesIO
from tkinter import filedialog
from .progress_dialog import ProgressDialog
import threading

class ObjectList(ttk.Frame):
    """对象列表组件"""
    def __init__(self, parent, oss_client=None):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        self.oss_client = oss_client
        self.current_path = ""  # 当前路径
        
        # 定义图标字符
        self.icons = {
            'folder': '📁',
            'file': '📄',
            'back': '⬆️'
        }
        
        # 配置样式
        style = ttk.Style()
        style.configure('Treeview', rowheight=24)  # 增加行高以适应Unicode字符
        
        self.create_widgets()
        if self.oss_client:
            self.load_objects()
    
    def create_widgets(self):
        """创建列表组件"""
        # 创建工具栏
        self.toolbar = ttk.Frame(self)
        self.toolbar.pack(fill=tk.X, padx=5, pady=(0, 5))
        
        # 添加路径导航
        self.path_var = tk.StringVar(value="/")
        self.path_entry = ttk.Entry(
            self.toolbar,
            textvariable=self.path_var,
            state='readonly'
        )
        self.path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # 刷新按钮
        self.refresh_btn = ttk.Button(
            self.toolbar,
            text="刷新",
            command=self.load_objects
        )
        self.refresh_btn.pack(side=tk.RIGHT, padx=(5, 0))
        
        # 创建对象列表
        self.tree = ttk.Treeview(
            self,
            columns=('icon', 'name', 'size', 'type', 'modified'),  # 添加icon列
            show='headings',  # 改回只显示headings
            selectmode='extended'
        )
        
        # 设置列
        self.tree.heading('icon', text='')
        self.tree.heading('name', text='名称')
        self.tree.heading('size', text='大小')
        self.tree.heading('type', text='类型')
        self.tree.heading('modified', text='修改时间')
        
        # 调整列宽度
        self.tree.column('icon', width=30, minwidth=30, stretch=False)
        self.tree.column('name', width=300, minwidth=200)
        self.tree.column('size', width=100, minwidth=80)
        self.tree.column('type', width=100, minwidth=80)
        self.tree.column('modified', width=150, minwidth=120)
        
        # 添加滚动条
        scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        # 布局
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 绑定双击事件
        self.tree.bind('<Double-1>', self.on_double_click)
        
        # 创建右键菜单
        self.context_menu = tk.Menu(self, tearoff=0)
        self.context_menu.add_command(label="下载", command=self.download_selected)
        self.context_menu.add_command(label="删除", command=self.delete_selected)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="复制路径", command=self.copy_path)
        self.context_menu.add_command(label="刷新", command=self.load_objects)  # 添加刷新选项
        
        # 绑定右键菜单
        self.tree.bind('<Button-3>', self.show_context_menu)
    
    def load_objects(self, path=""):
        """加载指定路径下的对象"""
        try:
            # 清空现有项目
            for item in self.tree.get_children():
                self.tree.delete(item)
            
            if not self.oss_client:
                self.logger.warning("No OSS client configured")
                return
            
            # 更新当前路径
            self.current_path = path
            self.path_var.set(f"/{path}" if path else "/")
            
            # 获取对象列表
            objects = self.oss_client.list_objects(prefix=path)
            
            # 用分别存储目录和文件
            directories = []
            files = []
            
            # 首先识别所有目录和文件
            for obj in objects:
                name = obj['name']
                if path and name.startswith(path):
                    name = name[len(path):].lstrip('/')
                
                if not name:  # 跳过空名称
                    continue
                
                # 处理目录结构
                parts = name.split('/')
                if len(parts) > 1:
                    # 这是一个子目录中的文件
                    dir_name = parts[0]
                    if dir_name not in [d[0] for d in directories]:
                        directories.append((dir_name, '', '目录', ''))
                    continue
                
                # 处理直接文件和目录
                if obj['type'] == 'directory':
                    directories.append((name, '', '目录', ''))
                else:
                    files.append((
                        name,
                        self.format_size(obj.get('size', 0)),
                        self.get_file_type(name),
                        obj.get('last_modified', '')
                    ))
            
            # 添加返回上级目录项
            if path:
                self.tree.insert('', 0, values=(
                    self.icons['back'],
                    '..',
                    '',
                    '目录',
                    ''
                ), tags=('parent',))
            
            # 添加目录（排序后）
            for dir_info in sorted(directories, key=lambda x: x[0].lower()):
                self.tree.insert('', 'end', values=(
                    self.icons['folder'],
                    dir_info[0],
                    dir_info[1],
                    dir_info[2],
                    dir_info[3]
                ), tags=('directory',))
            
            # 添加文件（排序后）
            for file_info in sorted(files, key=lambda x: x[0].lower()):
                self.tree.insert('', 'end', values=(
                    self.icons['file'],
                    file_info[0],
                    file_info[1],
                    file_info[2],
                    file_info[3]
                ), tags=('file',))
            
            self.logger.info(f"Loaded objects at path: '{path}'")
            
        except Exception as e:
            self.logger.error(f"Failed to load objects: {str(e)}")
            messagebox.showerror("错误", f"加载对象失败: {str(e)}")
    
    def on_double_click(self, event):
        """处理双击事件"""
        item = self.tree.selection()[0]
        values = self.tree.item(item)['values']
        if not values:
            return
            
        name = values[1]
        if name == '..':  # 返回上级目录
            parent_path = '/'.join(self.current_path.split('/')[:-1])
            self.load_objects(parent_path)
        elif 'directory' in self.tree.item(item)['tags']:  # 进入目录
            new_path = f"{self.current_path}/{name}".lstrip('/')
            self.load_objects(new_path)
    
    def show_context_menu(self, event):
        """显示右键菜单"""
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            self.context_menu.post(event.x_root, event.y_root)
    
    def download_selected(self):
        """下载选中的对象"""
        selection = self.tree.selection()
        if not selection:
            return
        
        # 获取选中的项目
        items = []
        for item in selection:
            values = self.tree.item(item)['values']
            if values and values[1] != '..':
                name = values[1]
                is_dir = 'directory' in self.tree.item(item)['tags']
                items.append((name, is_dir))
        
        if not items:
            return
        
        # 选择下载目录
        download_dir = filedialog.askdirectory(
            title="选择下载目录",
            mustexist=True
        )
        
        if not download_dir:
            return
        
        # 创建进度对话框
        progress = ProgressDialog(
            self,
            title="下载进度",
            message=f"正在下载 {len(items)} 个项目"
        )
        
        # 在新线程中执行下载
        thread = threading.Thread(
            target=self._download_items,
            args=(items, download_dir, progress)
        )
        thread.daemon = True
        thread.start()
    
    def _download_items(self, items, download_dir, progress):
        """在后台线程中执行下载"""
        try:
            total_items = len(items)
            current_item = 0
            
            for name, is_dir in items:
                if progress.cancelled:
                    progress.file_var.set("已取消下载")
                    break
                
                full_path = f"{self.current_path}/{name}".lstrip('/')
                local_path = os.path.join(download_dir, name)
                
                if is_dir:
                    # 下载目录
                    self._download_directory(full_path, local_path, progress)
                else:
                    try:
                        # 获取文件大小
                        file_info = self.oss_client.get_object_info(full_path)
                        total_size = file_info.get('size', 0)
                        
                        # 创建进度回调
                        def progress_callback(transferred, total):
                            if not progress.cancelled:
                                percentage = (current_item + transferred/total) / total_items * 100
                                progress.update_progress(
                                    percentage,
                                    name,
                                    transferred,
                                    total
                                )
                        
                        # 下载文件
                        self.oss_client.download_file(
                            full_path,
                            local_path,
                            progress_callback=progress_callback
                        )
                    except Exception as e:
                        if progress.cancelled:
                            # 如果是取消导致的异常，删除未完成的文件
                            if os.path.exists(local_path):
                                os.remove(local_path)
                            break
                        else:
                            raise
                
                current_item += 1
            
            if progress.cancelled:
                progress.file_var.set("下载已取消")
            else:
                progress.update_progress(100, "下载完成")
                
        except Exception as e:
            self.logger.error(f"Download failed: {str(e)}")
            progress.file_var.set(f"下载失败: {str(e)}")
            progress.speed_var.set("")
        finally:
            # 延迟关闭进度对话框
            progress.after(1500, progress.destroy)
    
    def _download_directory(self, remote_dir, local_dir, progress):
        """下载整个目录"""
        try:
            os.makedirs(local_dir, exist_ok=True)
            objects = self.oss_client.list_objects(prefix=remote_dir)
            
            for obj in objects:
                if progress.cancelled:
                    break
                    
                name = obj['name']
                if obj['type'] != 'directory':
                    relative_path = name[len(remote_dir):].lstrip('/')
                    local_path = os.path.join(local_dir, relative_path)
                    
                    # 创建本地目录
                    os.makedirs(os.path.dirname(local_path), exist_ok=True)
                    
                    # 更新进度
                    progress.update_progress(
                        -1,  # 不确定的进度
                        f"正在下载: {relative_path}"
                    )
                    
                    # 下载文件
                    self.oss_client.download_file(name, local_path)
        
        except Exception as e:
            self.logger.error(f"Directory download failed: {str(e)}")
            raise
    
    def delete_selected(self):
        """删除选中的对象"""
        selection = self.tree.selection()
        if not selection:
            return
            
        # 获取选中的文件名
        items = []
        for item in selection:
            values = self.tree.item(item)['values']
            if values and values[1] != '..':
                items.append(values[1])
        
        if not items:
            return
            
        # 确认删除
        if messagebox.askyesno("确认", f"确定要删除选中的 {len(items)} 个项目吗？"):
            # TODO: 实现删除功能
            messagebox.showinfo("提示", "删除功能即将实现")
    
    def copy_path(self):
        """复制对象路径"""
        selection = self.tree.selection()
        if not selection:
            return
            
        # 获取完整路径
        item = self.tree.item(selection[0])
        name = item['values'][1]
        if name == '..':
            return
            
        full_path = f"{self.current_path}/{name}".lstrip('/')
        
        # 复制到剪贴板
        self.clipboard_clear()
        self.clipboard_append(full_path)
        self.status_message = f"已复制路径: {full_path}"
    
    @staticmethod
    def format_size(size):
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"
    
    @staticmethod
    def get_file_type(filename):
        """获取文件类型"""
        if '.' not in filename:
            return '文件'
        return filename.split('.')[-1].upper()
    
    def set_oss_client(self, client):
        """设置OSS客户端"""
        self.oss_client = client
        self.load_objects() 