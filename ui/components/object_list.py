import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import logging
from PIL import Image, ImageTk
import os
import base64
from io import BytesIO
from tkinter import filedialog
from .progress_dialog import ProgressDialog
import threading
from .toast import Toast  # 添加导入

# 尝试导入 tkinterdnd2，如果不可用则禁用拖放功能
try:
    import tkinterdnd2
    DRAG_DROP_SUPPORTED = True
except ImportError:
    DRAG_DROP_SUPPORTED = False
    logging.warning("tkinterdnd2 not available, drag and drop will be disabled")

class ObjectList(ttk.Frame):
    """对象列表组件"""
    def __init__(self, parent, oss_client=None):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        self.oss_client = oss_client
        self.current_path = ""
        
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
        # 延迟加载对象列表
        if self.oss_client:
            self.after(100, self.load_objects)  # 使用 after 延迟加载
    
    def create_widgets(self):
        """创建列表组件"""
        # 创建工具栏
        self.toolbar = ttk.Frame(self)
        self.toolbar.pack(fill=tk.X, padx=5, pady=(0, 5))
        
        # 添加上传按钮
        self.upload_btn = ttk.Button(
            self.toolbar,
            text="上传",
            command=self.start_upload
        )
        self.upload_btn.pack(side=tk.LEFT, padx=2)
        
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
        self.context_menu.add_command(label="重命名", command=self.rename_selected)
        self.context_menu.add_command(label="删除", command=self.delete_selected)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="新建文件夹", command=self.create_folder)
        self.context_menu.add_command(label="新建文本文件", command=self.create_text_file)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="复制路径", command=self.copy_path)
        self.context_menu.add_command(label="复制URL", command=self.copy_url)
        self.context_menu.add_command(label="刷新", command=self.load_objects)
        
        # 绑定右键菜单
        self.tree.bind('<Button-3>', self.show_context_menu)
        
        # 启用拖放功能（如果支持）
        if DRAG_DROP_SUPPORTED:
            self.tree.drop_target_register('DND_Files')
            self.tree.dnd_bind('<<Drop>>', self.on_drop)
    
    def load_objects(self, path: str = ""):
        """加载对象列表"""
        try:
            self.logger.info(f"Loading objects from path: {path}")
            if hasattr(self.oss_client, 'proxy_settings'):
                self.logger.info(f"Current proxy settings: {self.oss_client.proxy_settings}")
            
            objects = self.oss_client.list_objects(prefix=path)
            
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
            directories = set()  # 使用集合避免重复
            files = []
            
            # 首先识别所有目录和文件
            for obj in objects:
                name = obj['name']
                
                # 跳过当前目录
                if name == path or (path and not name.startswith(path + '/')):
                    continue
                
                # 获取相对路径
                relative_path = name[len(path):].lstrip('/') if path else name
                
                # 处理目录
                if obj['type'] == 'directory' or name.endswith('/'):
                    # 只取第一级目录
                    dir_name = relative_path.split('/')[0]
                    if dir_name:
                        directories.add(dir_name)
                # 处理文件
                elif '/' not in relative_path:  # 只显示当前目录的文件
                    files.append((
                        relative_path,
                        self.format_size(obj.get('size', 0)),
                        self.get_file_type(relative_path),
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
            for dir_name in sorted(directories):
                self.tree.insert('', 'end', values=(
                    self.icons['folder'],
                    dir_name,
                    '',
                    '目录',
                    ''
                ), tags=('directory',))
            
            # 添加文件（排序后）
            for file_info in sorted(files, key=lambda x: x[0].lower()):
                self.tree.insert('', 'end', values=(
                    self.icons['file'],
                    file_info[0],
                    file_info[1],
                    file_info[2],
                    file_info[3]
                ))
            
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
            
        name = values[1]  # 获取原始名称，不做任何转换
        if name == '..':  # 返回上级目录
            parent_path = '/'.join(self.current_path.split('/')[:-1])
            self.load_objects(parent_path)
        elif 'directory' in self.tree.item(item)['tags']:  # 进入目录
            # 保持原始名称，不要做任何数值转换
            new_path = f"{self.current_path}/{name}".lstrip('/')
            # 记录日志以便调试
            self.logger.debug(f"Entering directory: {name} -> {new_path}")
            self.load_objects(new_path)
    
    def show_context_menu(self, event):
        """显示右键菜单"""
        # 获取点击位置的项目
        clicked_item = self.tree.identify_row(event.y)
        if not clicked_item:
            return
            
        # 如果点击的项目不在当前选中项中，则更新选择
        if clicked_item not in self.tree.selection():
            self.tree.selection_set(clicked_item)
        
        # 显示菜单
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
                        total_size = int(file_info.get('size', 0))
                        
                        # 创建进度回调
                        def progress_callback(transferred, total):
                            if not progress.cancelled:
                                progress.update_progress(
                                    transferred,
                                    total,
                                    name
                                )
                        
                        # 下载文件
                        self.oss_client.download_file(
                            full_path,
                            local_path,
                            progress_callback=progress_callback
                        )
                    except Exception as e:
                        if progress.cancelled:
                            if os.path.exists(local_path):
                                os.remove(local_path)
                            break
                        else:
                            raise
                
                current_item += 1
            
            if progress.cancelled:
                progress.file_var.set("下载已取消")
            else:
                progress.update_progress(100, 100, "下载完成")
                
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
            
        # 获取选中的项目
        items_to_delete = []
        for item in selection:
            values = self.tree.item(item)['values']
            if values and values[1] != '..':  # 排除返回上级目录项
                name = values[1]
                is_dir = values[3] == '目录'
                full_path = f"{self.current_path}/{name}".lstrip('/')
                items_to_delete.append((full_path, is_dir))
        
        if not items_to_delete:
            return
            
        # 确认删除
        count = len(items_to_delete)
        if not messagebox.askyesno(
            "确认删除",
            f"确定要删除选中的 {count} 个项目吗？\n此操作不可恢复！",
            icon='warning'
        ):
            return
            
        # 创建进度对话框
        progress = ProgressDialog(self, "删除", "正在删除...")
        
        # 在后台线程中执行删除
        thread = threading.Thread(
            target=self._delete_items,
            args=(items_to_delete, progress)
        )
        thread.daemon = True
        thread.start()
    
    def _delete_items(self, items, progress):
        """在后台线程中执行删除"""
        try:
            total_items = len(items)
            for i, (path, is_dir) in enumerate(items, 1):
                if progress.cancelled:
                    break
                    
                try:
                    # 更新进度
                    progress.update_progress(
                        i, total_items,
                        f"正在删除: {path}"
                    )
                    
                    if is_dir:
                        # 删除目录
                        objects = self.oss_client.list_objects(prefix=path)
                        for obj in objects:
                            if progress.cancelled:
                                break
                            self.oss_client.delete_file(obj['name'])
                    else:
                        # 删除文件
                        self.oss_client.delete_file(path)
                        
                except Exception as e:
                    self.logger.error(f"Failed to delete {path}: {str(e)}")
                    if not messagebox.askyesno(
                        "删除错误",
                        f"删除 {path} 失败: {str(e)}\n是否继续删除其他项目？"
                    ):
                        break
            
            if progress.cancelled:
                progress.file_var.set("已取消删除")
            else:
                progress.file_var.set("删除完成")
                self.load_objects(self.current_path)  # 刷新列表
                
        except Exception as e:
            self.logger.error(f"Delete operation failed: {str(e)}")
            progress.file_var.set(f"删除失败: {str(e)}")
        finally:
            # 延迟关闭进度对话框
            progress.after(1500, progress.destroy)
    
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
    
    def _upload_thread(self, local_file, object_name):
        try:
            # 获取文件大小和计算分片信息
            file_size = os.path.getsize(local_file)
            chunk_size = 5 * 1024 * 1024  # 5MB
            is_multipart = file_size > chunk_size
            
            # 正确计算分片数量
            total_parts = (file_size + chunk_size - 1) // chunk_size if is_multipart else 0
            
            self.logger.info(f"Starting upload: {object_name}, size: {file_size}, parts: {total_parts}")
            
            # 创建进度窗口
            progress_win = ProgressDialog(
                self,
                f"上传 {object_name}",
                multipart=is_multipart,
                total_parts=total_parts
            )
            
            def progress_callback(transferred, total, part_number=None, part_transferred=None, part_total=None):
                progress_win.update_progress(transferred, total)
                if part_number is not None:
                    progress_win.update_part_progress(part_number, part_transferred, part_total)
            
            # 构建完整的远程路径（考虑当前目录）
            if self.current_path:
                remote_path = f"{self.current_path}/{object_name}".lstrip('/')
            else:
                remote_path = object_name
            
            # 使用传输管理器上传
            from utils.transfer_manager import TransferManager
            manager = TransferManager(chunk_size=chunk_size)  # 确保使用相同的分片大小
            manager.upload_file(
                self.oss_client,
                local_file,
                remote_path,
                progress_callback=progress_callback
            )
            
            progress_win.close()
            self.load_objects(self.current_path)  # 刷新当前目录
            
            # 使用 Toast 替代 messagebox
            Toast(self, f"上传成功: {object_name}")
            
        except Exception as e:
            self.logger.error(f"Upload failed: {str(e)}")
            messagebox.showerror("错误", f"上传失败: {str(e)}")
    
    def start_upload(self):
        """通过文件对话框选择文件上传"""
        files = filedialog.askopenfilenames(
            title="选择要上传的文件",
            multiple=True
        )
        if files:
            for file_path in files:
                object_name = os.path.basename(file_path)
                thread = threading.Thread(
                    target=self._upload_thread,
                    args=(file_path, object_name)
                )
                thread.daemon = True
                thread.start()
    
    def on_drop(self, event):
        """处理文件拖放"""
        try:
            files = self.tree.tk.splitlist(event.data)
            for file_path in files:
                if os.path.isfile(file_path):  # 只处理文件
                    object_name = os.path.basename(file_path)
                    thread = threading.Thread(
                        target=self._upload_thread,
                        args=(file_path, object_name)
                    )
                    thread.daemon = True
                    thread.start()
        except Exception as e:
            self.logger.error(f"Drop failed: {str(e)}")
            messagebox.showerror("错误", f"拖放上传失败: {str(e)}") 
    
    def rename_selected(self):
        """重命名选中的对象"""
        selection = self.tree.selection()
        if not selection or len(selection) != 1:  # 只允许单个重命名
            return
            
        item = self.tree.item(selection[0])
        values = item['values']
        if not values or values[1] == '..':  # 排除返回上级目录项
            return
            
        old_name = values[1]
        is_dir = values[3] == '目录'
        old_path = f"{self.current_path}/{old_name}".lstrip('/')
        
        # 弹出重命名对话框
        new_name = self.show_rename_dialog(old_name)
        if not new_name or new_name == old_name:
            return
            
        # 构建新路径
        new_path = f"{self.current_path}/{new_name}".lstrip('/')
        
        try:
            if is_dir:
                # 重命名目录（移动所有文件）
                self.oss_client.rename_folder(old_path, new_path)
            else:
                # 重命名文件（复制后删除）
                self.oss_client.rename_object(old_path, new_path)
            
            # 刷新列表
            self.load_objects(self.current_path)
            
            # 显示成功提示
            Toast(self, f"重命名成功: {old_name} → {new_name}")
            
        except Exception as e:
            self.logger.error(f"Failed to rename {old_path} to {new_path}: {str(e)}")
            messagebox.showerror("错误", f"重命名失败: {str(e)}")
    
    def show_rename_dialog(self, old_name):
        """显示重命名对话框"""
        dialog = tk.Toplevel(self)
        dialog.title("重命名")
        dialog.geometry("500x150")  # 增加宽度和高度
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()
        
        # 居中显示
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() - dialog.winfo_width()) // 2
        y = (dialog.winfo_screenheight() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")
        
        # 创建主框架
        main_frame = ttk.Frame(dialog, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 创建输入区域
        input_frame = ttk.Frame(main_frame)
        input_frame.pack(fill=tk.BOTH, expand=True)
        
        # 标签和输入框
        ttk.Label(input_frame, text="新名称:").pack(anchor=tk.W, pady=(0, 5))
        entry = ttk.Entry(input_frame, width=60)
        entry.pack(fill=tk.X, pady=(0, 20))
        entry.insert(0, old_name)
        
        # 智能选择文件名部分
        if '.' in old_name:
            name_part = old_name.rpartition('.')[0]  # 获取最后一个点之前的部分
            entry.select_range(0, len(name_part))
        else:
            entry.select_range(0, len(old_name))
        
        # 按钮框架
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(0, 10))
        
        result = [None]
        
        def on_ok():
            result[0] = entry.get().strip()
            dialog.destroy()
            
        def on_cancel():
            dialog.destroy()
        
        # 按钮
        cancel_btn = ttk.Button(button_frame, text="取消", command=on_cancel, width=10)
        ok_btn = ttk.Button(button_frame, text="确定", command=on_ok, width=10)
        
        # 从右向左布局按钮
        ok_btn.pack(side=tk.RIGHT, padx=(5, 0))
        cancel_btn.pack(side=tk.RIGHT)
        
        # 绑定回车键和ESC键
        entry.bind('<Return>', lambda e: on_ok())
        entry.bind('<Escape>', lambda e: on_cancel())
        dialog.bind('<Escape>', lambda e: on_cancel())
        
        # 设置焦点
        entry.focus_set()
        
        # 等待窗口关闭
        dialog.wait_window()
        return result[0] 
    
    def copy_url(self):
        """复制对象的公共URL"""
        selection = self.tree.selection()
        if not selection:
            return
            
        # 只处理第一个选中项
        item = self.tree.item(selection[0])
        values = item['values']
        if not values or values[1] == '..' or values[3] == '目录':
            return
            
        try:
            # 获取完整路径
            name = values[1]
            full_path = f"{self.current_path}/{name}".lstrip('/')
            
            # 获取公共URL
            url = self.oss_client.get_public_url(full_path)
            
            # 复制到剪贴板
            self.clipboard_clear()
            self.clipboard_append(url)
            
            # 显示提示
            Toast(self, f"已复制URL: {url}")
            
        except Exception as e:
            self.logger.error(f"Failed to get URL for {full_path}: {str(e)}")
            messagebox.showerror("错误", f"获取URL失败: {str(e)}") 
    
    def create_folder(self):
        """创建新文件夹"""
        dialog = tk.Toplevel(self)
        dialog.title("新建文件夹")
        dialog.geometry("400x120")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()
        
        # 居中显示
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() - dialog.winfo_width()) // 2
        y = (dialog.winfo_screenheight() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")
        
        # 创建主框架
        main_frame = ttk.Frame(dialog, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 标签和输入框
        ttk.Label(main_frame, text="文件夹名称:").pack(anchor=tk.W, pady=(0, 5))
        entry = ttk.Entry(main_frame, width=40)
        entry.pack(fill=tk.X, pady=(0, 20))
        entry.insert(0, "新建文件夹")
        entry.select_range(0, len("新建文件夹"))
        
        result = [None]
        
        def on_ok():
            folder_name = entry.get().strip()
            if folder_name:
                result[0] = folder_name
                dialog.destroy()
            
        def on_cancel():
            dialog.destroy()
        
        # 按钮框架
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X)
        
        # 按钮
        cancel_btn = ttk.Button(button_frame, text="取消", command=on_cancel, width=10)
        ok_btn = ttk.Button(button_frame, text="确定", command=on_ok, width=10)
        
        # 从右向左布局按钮
        ok_btn.pack(side=tk.RIGHT, padx=(5, 0))
        cancel_btn.pack(side=tk.RIGHT)
        
        # 绑定回车键和ESC键
        entry.bind('<Return>', lambda e: on_ok())
        entry.bind('<Escape>', lambda e: on_cancel())
        dialog.bind('<Escape>', lambda e: on_cancel())
        
        # 设置焦点
        entry.focus_set()
        
        # 等待窗口关闭
        dialog.wait_window()
        
        # 创建文件夹
        folder_name = result[0]
        if folder_name:
            try:
                # 构建完整路径
                full_path = f"{self.current_path}/{folder_name}".lstrip('/')
                if full_path[-1] != '/':
                    full_path += '/'
                    
                # 创建空对象作为文件夹标记
                self.oss_client.create_folder(full_path)
                
                # 刷新列表
                self.load_objects(self.current_path)
                
                # 显示成功提示
                Toast(self, f"已创建文件夹: {folder_name}")
                
            except Exception as e:
                self.logger.error(f"Failed to create folder {folder_name}: {str(e)}")
                messagebox.showerror("错误", f"创建文件夹失败: {str(e)}") 
    
    def create_text_file(self):
        """创建新文本文件"""
        dialog = tk.Toplevel(self)
        dialog.title("新建文本文件")
        dialog.geometry("500x400")  # 更大的窗口以容纳文本编辑区
        dialog.resizable(True, True)  # 允许调整大小
        dialog.transient(self)
        dialog.grab_set()
        
        # 居中显示
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() - dialog.winfo_width()) // 2
        y = (dialog.winfo_screenheight() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")
        
        # 创建主框架
        main_frame = ttk.Frame(dialog, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 文件名输入区域
        name_frame = ttk.Frame(main_frame)
        name_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(name_frame, text="文件名:").pack(side=tk.LEFT)
        name_entry = ttk.Entry(name_frame, width=40)
        name_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))
        name_entry.insert(0, "新建文本文档.txt")
        name_entry.select_range(0, len("新建文本文档"))
        
        # 创建文本编辑区
        text_frame = ttk.Frame(main_frame)
        text_frame.pack(fill=tk.BOTH, expand=True)
        
        text_area = tk.Text(text_frame, wrap=tk.WORD, width=50, height=15)
        text_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 添加滚动条
        scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=text_area.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        text_area.configure(yscrollcommand=scrollbar.set)
        
        result = {"name": None, "content": None}
        
        def on_ok():
            file_name = name_entry.get().strip()
            if not file_name:
                messagebox.showwarning("警告", "请输入文件名")
                return
                
            # 确保文件名以.txt结尾
            if not file_name.lower().endswith('.txt'):
                file_name += '.txt'
                
            result["name"] = file_name
            result["content"] = text_area.get("1.0", tk.END)
            dialog.destroy()
            
        def on_cancel():
            dialog.destroy()
        
        # 按钮框架
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        # 按钮
        cancel_btn = ttk.Button(button_frame, text="取消", command=on_cancel, width=10)
        ok_btn = ttk.Button(button_frame, text="确定", command=on_ok, width=10)
        
        # 从右向左布局按钮
        ok_btn.pack(side=tk.RIGHT, padx=(5, 0))
        cancel_btn.pack(side=tk.RIGHT)
        
        # 绑定快捷键
        dialog.bind('<Escape>', lambda e: on_cancel())
        dialog.bind('<Control-Return>', lambda e: on_ok())  # Ctrl+Enter 保存
        
        # 设置焦点
        name_entry.focus_set()
        
        # 等待窗口关闭
        dialog.wait_window()
        
        # 创建文件
        if result["name"] and result["content"] is not None:
            try:
                # 构建完整路径
                full_path = f"{self.current_path}/{result['name']}".lstrip('/')
                
                # 将文本内容转换为字节流
                content_bytes = result["content"].encode('utf-8')
                
                # 直接上传内容
                self.oss_client.put_object(
                    full_path,
                    content_bytes,
                    content_type='text/plain'
                )
                
                # 刷新列表
                self.load_objects(self.current_path)
                
                # 显示成功提示
                Toast(self, f"已创建文件: {result['name']}")
                
            except Exception as e:
                self.logger.error(f"Failed to create text file {result['name']}: {str(e)}")
                messagebox.showerror("错误", f"创建文件失败: {str(e)}") 