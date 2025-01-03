# ui/main_window.py
# 使用 Tkinter 创建主窗口
# 首先，创建一个主窗口，包含菜单栏、工具栏和主内容区。使用ttk.Notebook可以实现多标签页，便于在不同的OSS源之间切换。

import tkinter as tk
from tkinter import ttk, messagebox
import logging
from utils.config_manager import ConfigManager
from .components.bucket_list import BucketList
from .components.object_list import ObjectList
import os
import urllib3

try:
    import tkinterdnd2 as tkdnd
    DRAG_DROP_SUPPORTED = True
except ImportError:
    import tkinter as tk
    DRAG_DROP_SUPPORTED = False
    logging.warning("tkinterdnd2 not available, drag and drop will be disabled")

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class MainWindow(tkdnd.Tk if DRAG_DROP_SUPPORTED else tk.Tk):
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        
        # 1. 先加载代理设置
        self._load_proxy_settings()
        
        # 2. 再初始化配置管理器
        self.config_manager = ConfigManager()
        self.config_manager.main_window = self
        self.oss_clients = self.config_manager.oss_clients
        
        # 3. 最后创建UI
        self.title("OSS Explorer")
        self.geometry("1024x768")
        self.minsize(800, 600)
        
        self.create_menu()
        self.create_main_frame()
        self.create_status_bar()
        
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.logger.info("Main window initialized")
    
    def _load_proxy_settings(self):
        """加载并应用代理设置"""
        try:
            from utils.settings_manager import SettingsManager  # 添加导入
            from utils.proxy_manager import ProxyManager
            
            settings_manager = SettingsManager()
            proxy_manager = ProxyManager()
            
            settings = settings_manager.load_settings()
            self.logger.info(f"Proxy settings in config: {settings.get('proxy', {})}")
            
            proxy_settings = settings_manager.get_proxy_settings()
            self.logger.info(f"Loaded proxy settings: {proxy_settings}")
            
            proxy_manager.set_proxy(proxy_settings)
            self.logger.info(f"Applied proxy settings: {proxy_manager.get_proxy()}")
            
            # 检查环境变量
            env_proxies = {
                'HTTP_PROXY': os.environ.get('HTTP_PROXY'),
                'HTTPS_PROXY': os.environ.get('HTTPS_PROXY'),
                'http_proxy': os.environ.get('http_proxy'),
                'https_proxy': os.environ.get('https_proxy')
            }
            self.logger.info(f"Current proxy environment variables: {env_proxies}")
            
        except Exception as e:
            self.logger.error(f"Failed to load proxy settings: {str(e)}", exc_info=True)
        
    def create_menu(self):
        """创建菜单栏"""
        self.menubar = tk.Menu(self)
        self.config(menu=self.menubar)
        
        # 文件菜单
        self.file_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label="文件", menu=self.file_menu)
        self.file_menu.add_command(label="设置", command=self.show_settings)
        self.file_menu.add_separator()
        self.file_menu.add_command(label="退出", command=self.quit)
        
        # 帮助菜单
        help_menu = tk.Menu(self.menubar, tearoff=0)
        help_menu.add_command(label="关于", command=self.show_about)
        self.menubar.add_cascade(label="帮助", menu=help_menu)
        
    def create_main_frame(self):
        """创建主框架"""
        # 创建主容器
        self.main_container = ttk.Frame(self)
        self.main_container.pack(expand=True, fill=tk.BOTH)
        
        # 创建顶部工具栏框架
        self.toolbar_frame = ttk.Frame(self.main_container)
        self.toolbar_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # 获取可用的客户端列表
        available_clients = self.config_manager.get_available_clients()
        if available_clients:
            # 创建OSS源选择框
            ttk.Label(self.toolbar_frame, text="OSS源:").pack(side=tk.LEFT, padx=(5, 2))
            self.source_var = tk.StringVar()
            self.source_combo = ttk.Combobox(
                self.toolbar_frame,
                textvariable=self.source_var,
                values=available_clients,
                state='readonly',
                width=20
            )
            self.source_combo.pack(side=tk.LEFT, padx=2)
            self.source_combo.bind('<<ComboboxSelected>>', self.on_source_change)
            
            # 默认选择第一个源
            first_source = available_clients[0]
            self.source_combo.set(first_source)
            
            # 初始化第一个客户端
            client = self.config_manager.get_client(first_source)
            if client:
                # 创建内容区域框架
                self.content_frame = ttk.Frame(self.main_container)
                self.content_frame.pack(expand=True, fill=tk.BOTH, padx=5, pady=5)
                
                # 创建水平分隔窗格
                self.paned = ttk.PanedWindow(self.content_frame, orient=tk.HORIZONTAL)
                self.paned.pack(expand=True, fill=tk.BOTH)
                
                # 创建存储桶列表（左侧）
                bucket_frame = ttk.Frame(self.paned)
                self.bucket_list = BucketList(bucket_frame, client)  # 使用新获取的客户端
                self.bucket_list.pack(expand=True, fill=tk.BOTH)
                
                # 创建对象列表（右侧）
                object_frame = ttk.Frame(self.paned)
                self.object_list = ObjectList(object_frame, client)  # 使用新获取的客户端
                self.object_list.pack(expand=True, fill=tk.BOTH)
                
                # 添加到分隔窗格
                self.paned.add(bucket_frame, weight=1)
                self.paned.add(object_frame, weight=3)
                
                # 绑定存储桶选择事件
                self.bucket_list.tree.bind('<<TreeviewSelect>>', self.on_bucket_select)
                
                # 更新状态栏
                self.status_message = f"当前OSS源: {first_source}"
            else:
                messagebox.showwarning("警告", f"无法连接到 {first_source}")
                # 显示错误信息
                ttk.Label(
                    self.main_container,
                    text=f"无法连接到 {first_source}\n请检查网络连接或配置",
                    font=('Helvetica', 12)
                ).pack(expand=True)
        else:
            # 显示提示信息
            ttk.Label(
                self.main_container,
                text="请在config.json中配置OSS客户端",
                font=('Helvetica', 12)
            ).pack(expand=True)
            self.status_message = "未找到OSS配置"
    
    def create_status_bar(self):
        """创建状态栏"""
        self.status_bar = ttk.Label(
            self,
            text=getattr(self, 'status_message', '就绪'),
            relief=tk.SUNKEN,
            anchor=tk.W
        )
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
    
    def on_source_change(self, event):
        """处理OSS源切换事件"""
        selected = self.source_var.get()
        if selected and self.bucket_list and self.object_list:
            try:
                # 获取新的客户端
                client = self.config_manager.get_client(selected)
                if not client:
                    raise ConnectionError(f"无法连接到 {selected}")
                
                # 更新两个列表的客户端
                self.bucket_list.set_oss_client(client)
                self.object_list.set_oss_client(client)
                self.status_bar.config(text=f"当前OSS源: {selected}")
                self._last_source = selected
            except Exception as e:
                self.logger.error(f"Failed to switch OSS source: {str(e)}")
                messagebox.showerror(
                    "错误",
                    f"切换到 {selected} 失败: {str(e)}\n请检查网络连接或配置"
                )
                # 恢复到上一个选择
                if hasattr(self, '_last_source'):
                    self.source_var.set(self._last_source)
    
    def show_about(self):
        """显示关于对话框"""
        messagebox.showinfo(
            "关于",
            "OSS Explorer\n版本 1.0\n统一对象存储浏览器"
        )
    
    def on_closing(self):
        """处理窗口关闭事件"""
        self.logger.info("Application closing")
        self.quit()
    
    def on_bucket_select(self, event):
        """处理存储桶选择事件"""
        selection = self.bucket_list.tree.selection()
        if selection:
            item = self.bucket_list.tree.item(selection[0])
            bucket_name = item['values'][0]
            self.status_bar.config(text=f"当前存储桶: {bucket_name}")
            # 加载对象列表
            self.object_list.load_objects()
    
    def show_settings(self):
        """显示设置对话框"""
        from .components.settings_dialog import SettingsDialog
        dialog = SettingsDialog(self)
        dialog.wait_window()
    
    def update_oss_clients(self, new_clients):
        """更新OSS客户端列表"""
        self.oss_clients = new_clients
        
        # 更新下拉列表的值
        if hasattr(self, 'source_combo'):
            current = self.source_var.get()
            self.source_combo['values'] = list(new_clients.keys())
            
            # 如果当前选中的源仍然存在，保持选中
            if current in new_clients:
                self.source_combo.set(current)
            # 否则选择第一个可用的源
            elif new_clients:
                self.source_combo.set(list(new_clients.keys())[0])