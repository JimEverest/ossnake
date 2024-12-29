import tkinter as tk
from tkinter import ttk, messagebox
import logging
from utils.settings_manager import SettingsManager
from utils.config_manager import ConfigManager

class SettingsDialog(tk.Toplevel):
    """设置对话框"""
    
    def __init__(self, parent):
        super().__init__(parent)
        self.title("设置")
        self.geometry("600x400")
        self.resizable(True, True)
        
        # 设置模态
        self.transient(parent)
        self.grab_set()
        
        # 初始化日志
        self.logger = logging.getLogger(__name__)
        
        # 初始化设置管理器
        self.settings_manager = SettingsManager()
        
        # 加载配置管理器
        self.config_manager = ConfigManager()
        
        # 创建主框架
        self.main_frame = ttk.Frame(self, padding="10")
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 创建标签页
        self.notebook = ttk.Notebook(self.main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 基础设置页
        self.basic_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.basic_frame, text="基础设置")
        
        # 高级设置页
        self.advanced_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.advanced_frame, text="高级设置")
        
        # 主题设置页
        self.theme_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.theme_frame, text="主题设置")
        
        # 按钮框架
        self.button_frame = ttk.Frame(self.main_frame)
        self.button_frame.pack(fill=tk.X, pady=(10, 0))
        
        # 确定取消按钮
        self.ok_button = ttk.Button(
            self.button_frame, 
            text="确定", 
            command=self.on_ok,
            width=10
        )
        self.cancel_button = ttk.Button(
            self.button_frame, 
            text="取消", 
            command=self.on_cancel,
            width=10
        )
        
        self.ok_button.pack(side=tk.RIGHT, padx=(5, 0))
        self.cancel_button.pack(side=tk.RIGHT)
        
        # 居中显示
        self.center_window()
        
        # 创建基础设置页的内容
        self._create_basic_settings()
        self._create_theme_settings()  # 添加主题设置页
        self._create_advanced_settings()  # 添加高级设置页
        
        # 创建UI后加载设置
        self.load_settings()
        
    def center_window(self):
        """居中显示窗口"""
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'{width}x{height}+{x}+{y}')
        
    def on_ok(self):
        """确定按钮回调"""
        if self.save_settings():
            self.destroy()
        else:
            messagebox.showerror("错误", "保存设置失败")
        
    def on_cancel(self):
        """取消按钮回调"""
        self.destroy() 
        
    def _create_basic_settings(self):
        """创建基础设置页内容"""
        # 使用滚动框架
        canvas = tk.Canvas(self.basic_frame)
        scrollbar = ttk.Scrollbar(self.basic_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw", width=550)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # 代理设置组
        proxy_frame = ttk.LabelFrame(scrollable_frame, text="代理设置", padding="5")
        proxy_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # 代理开关
        self.proxy_enabled_var = tk.BooleanVar(value=False)
        proxy_cb = ttk.Checkbutton(
            proxy_frame,
            text="启用代理",
            variable=self.proxy_enabled_var,
            command=self._on_proxy_toggle
        )
        proxy_cb.pack(anchor=tk.W)
        
        # HTTP代理设置
        self.http_proxy_frame = ttk.Frame(proxy_frame)
        self.http_proxy_frame.pack(fill=tk.X, pady=2)
        ttk.Label(self.http_proxy_frame, text="HTTP代理:").pack(side=tk.LEFT)
        self.http_proxy_var = tk.StringVar()
        self.http_proxy_entry = ttk.Entry(self.http_proxy_frame, textvariable=self.http_proxy_var)
        self.http_proxy_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        # HTTPS代理设置
        self.https_proxy_frame = ttk.Frame(proxy_frame)
        self.https_proxy_frame.pack(fill=tk.X, pady=2)
        ttk.Label(self.https_proxy_frame, text="HTTPS代理:").pack(side=tk.LEFT)
        self.https_proxy_var = tk.StringVar()
        self.https_proxy_entry = ttk.Entry(self.https_proxy_frame, textvariable=self.https_proxy_var)
        self.https_proxy_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        # API设置组
        api_frame = ttk.LabelFrame(scrollable_frame, text="API设置", padding="5")
        api_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # API开关
        self.api_enabled_var = tk.BooleanVar(value=False)
        api_cb = ttk.Checkbutton(
            api_frame,
            text="启用API服务",
            variable=self.api_enabled_var,
            command=self._on_api_toggle
        )
        api_cb.pack(anchor=tk.W)
        
        # API设置框架
        self.api_settings_frame = ttk.Frame(api_frame)
        self.api_settings_frame.pack(fill=tk.X, pady=2)
        
        # API端口
        port_frame = ttk.Frame(self.api_settings_frame)
        port_frame.pack(fill=tk.X, pady=2)
        ttk.Label(port_frame, text="API端口:").pack(side=tk.LEFT)
        self.api_port_var = tk.StringVar(value="8000")
        port_entry = ttk.Entry(port_frame, width=8, textvariable=self.api_port_var)
        port_entry.pack(side=tk.LEFT, padx=5)
        
        # API默认OSS源选择
        oss_frame = ttk.Frame(self.api_settings_frame)
        oss_frame.pack(fill=tk.X, pady=2)
        ttk.Label(oss_frame, text="默认上传OSS源:").pack(side=tk.LEFT)
        self.api_oss_var = tk.StringVar()
        self.api_oss_combo = ttk.Combobox(
            oss_frame,
            textvariable=self.api_oss_var,
            values=list(self.load_oss_sources().keys()),  # 从config.json加载OSS源
            state='readonly'
        )
        self.api_oss_combo.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        # 上传设置组 (之前的代码)
        upload_frame = ttk.LabelFrame(scrollable_frame, text="上传设置", padding="5")
        upload_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # 分片上传设置
        self.multipart_upload_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            upload_frame,
            text="启用分片上传",
            variable=self.multipart_upload_var
        ).pack(anchor=tk.W)
        
        # 分片大小设置
        chunk_frame = ttk.Frame(upload_frame)
        chunk_frame.pack(fill=tk.X, pady=2)
        ttk.Label(chunk_frame, text="分片大小:").pack(side=tk.LEFT)
        self.chunk_size_var = tk.StringVar(value="5")
        chunk_entry = ttk.Entry(chunk_frame, width=10, textvariable=self.chunk_size_var)
        chunk_entry.pack(side=tk.LEFT, padx=5)
        ttk.Label(chunk_frame, text="MB").pack(side=tk.LEFT)
        
        # 上传并发数设置
        workers_frame = ttk.Frame(upload_frame)
        workers_frame.pack(fill=tk.X, pady=2)
        ttk.Label(workers_frame, text="上传并发数:").pack(side=tk.LEFT)
        self.upload_workers_var = tk.StringVar(value="4")
        workers_entry = ttk.Entry(workers_frame, width=5, textvariable=self.upload_workers_var)
        workers_entry.pack(side=tk.LEFT, padx=5)
        
        # 下载设置组 (之前的代码)
        download_frame = ttk.LabelFrame(scrollable_frame, text="下载设置", padding="5")
        download_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # 分片下载设置
        self.multipart_download_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            download_frame,
            text="启用分片下载",
            variable=self.multipart_download_var
        ).pack(anchor=tk.W)
        
        # 下载分片大小
        dl_chunk_frame = ttk.Frame(download_frame)
        dl_chunk_frame.pack(fill=tk.X, pady=2)
        ttk.Label(dl_chunk_frame, text="下载分片大小:").pack(side=tk.LEFT)
        self.download_chunk_size_var = tk.StringVar(value="5")
        dl_chunk_entry = ttk.Entry(dl_chunk_frame, width=10, textvariable=self.download_chunk_size_var)
        dl_chunk_entry.pack(side=tk.LEFT, padx=5)
        ttk.Label(dl_chunk_frame, text="MB").pack(side=tk.LEFT)
        
        # 下载并发数
        dl_workers_frame = ttk.Frame(download_frame)
        dl_workers_frame.pack(fill=tk.X, pady=2)
        ttk.Label(dl_workers_frame, text="下载并发数:").pack(side=tk.LEFT)
        self.download_workers_var = tk.StringVar(value="4")
        dl_workers_entry = ttk.Entry(
            dl_workers_frame, 
            width=5, 
            textvariable=self.download_workers_var
        )
        dl_workers_entry.pack(side=tk.LEFT, padx=5)
        
        # 默认设置组
        default_frame = ttk.LabelFrame(scrollable_frame, text="默认设置", padding="5")
        default_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # 默认OSS源
        default_oss_frame = ttk.Frame(default_frame)
        default_oss_frame.pack(fill=tk.X, pady=2)
        ttk.Label(default_oss_frame, text="默认OSS源:").pack(side=tk.LEFT)
        self.default_oss_var = tk.StringVar()
        self.default_oss_combo = ttk.Combobox(
            default_oss_frame,
            textvariable=self.default_oss_var,
            values=list(self.load_oss_sources().keys()),  # 从config.json加载OSS源
            state='readonly'
        )
        self.default_oss_combo.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        # 列表显示设置组
        list_frame = ttk.LabelFrame(scrollable_frame, text="列表显示设置", padding="5")
        list_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # 单次列举数量
        list_size_frame = ttk.Frame(list_frame)
        list_size_frame.pack(fill=tk.X, pady=2)
        ttk.Label(list_size_frame, text="单次列举数量:").pack(side=tk.LEFT)
        self.list_size_var = tk.StringVar(value="1000")
        list_size_entry = ttk.Entry(list_size_frame, width=8, textvariable=self.list_size_var)
        list_size_entry.pack(side=tk.LEFT, padx=5)
        
        # 安全设置组
        security_frame = ttk.LabelFrame(scrollable_frame, text="安全设置", padding="5")
        security_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # 客户端加密
        self.client_encryption_var = tk.BooleanVar(value=False)
        encryption_cb = ttk.Checkbutton(
            security_frame,
            text="启用客户端加密（仅UI，功能待实现）",
            variable=self.client_encryption_var,
            command=self._on_encryption_toggle
        )
        encryption_cb.pack(anchor=tk.W)
        
        # 加密设置框架
        self.encryption_frame = ttk.Frame(security_frame)
        self.encryption_frame.pack(fill=tk.X, pady=2)
        
        # 加密方式
        method_frame = ttk.Frame(self.encryption_frame)
        method_frame.pack(fill=tk.X, pady=2)
        ttk.Label(method_frame, text="加密方式:").pack(side=tk.LEFT)
        self.encryption_method_var = tk.StringVar(value="AES-256")
        method_combo = ttk.Combobox(
            method_frame,
            values=["AES-256", "RSA-2048"],
            textvariable=self.encryption_method_var,
            state='readonly',
            width=15
        )
        method_combo.pack(side=tk.LEFT, padx=5)
        
        # 隐私传输
        self.secure_transfer_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            security_frame,
            text="启用隐私传输模式",
            variable=self.secure_transfer_var
        ).pack(anchor=tk.W)
        
        # 布局滚动区域
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # 初始化状态
        self._on_proxy_toggle()
        self._on_api_toggle()
        
    def _on_proxy_toggle(self):
        """处理代理开关切换"""
        state = 'normal' if self.proxy_enabled_var.get() else 'disabled'
        self.http_proxy_entry.configure(state=state)
        self.https_proxy_entry.configure(state=state)
        
    def _on_api_toggle(self):
        """处理API开关切换"""
        state = 'normal' if self.api_enabled_var.get() else 'disabled'
        for child in self.api_settings_frame.winfo_children():
            for widget in child.winfo_children():
                if widget.winfo_class() != 'TLabel':  # 不禁用标签
                    widget.configure(state=state)
        
    def _on_encryption_toggle(self):
        """处理加密开关切换"""
        state = 'normal' if self.client_encryption_var.get() else 'disabled'
        for child in self.encryption_frame.winfo_children():
            for widget in child.winfo_children():
                if widget.winfo_class() != 'TLabel':  # 不禁用标签
                    widget.configure(state=state)
        
    def _create_theme_settings(self):
        """创建主题设置页内容"""
        # 主题选择框架
        theme_select_frame = ttk.LabelFrame(self.theme_frame, text="主题选择", padding="10")
        theme_select_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # 主题模式选择
        mode_frame = ttk.Frame(theme_select_frame)
        mode_frame.pack(fill=tk.X, pady=5)
        
        self.theme_mode_var = tk.StringVar(value="system")
        ttk.Radiobutton(
            mode_frame,
            text="跟随系统",
            value="system",
            variable=self.theme_mode_var
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Radiobutton(
            mode_frame,
            text="浅色",
            value="light",
            variable=self.theme_mode_var
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Radiobutton(
            mode_frame,
            text="深色",
            value="dark",
            variable=self.theme_mode_var
        ).pack(side=tk.LEFT, padx=5)
        
        # 主题颜色选择
        color_frame = ttk.Frame(theme_select_frame)
        color_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(color_frame, text="主题色:").pack(side=tk.LEFT)
        self.theme_color_var = tk.StringVar(value="blue")
        colors = ["blue", "green", "purple", "orange", "red"]
        
        for color in colors:
            ttk.Radiobutton(
                color_frame,
                text=color.capitalize(),
                value=color,
                variable=self.theme_color_var
            ).pack(side=tk.LEFT, padx=5)
        
        # 预览框架
        preview_frame = ttk.LabelFrame(self.theme_frame, text="预览", padding="10")
        preview_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # 添加一些示例控件用于预览
        ttk.Label(preview_frame, text="这是一个示例文本").pack(anchor=tk.W, pady=2)
        ttk.Entry(preview_frame).pack(fill=tk.X, pady=2)
        ttk.Button(preview_frame, text="示例按钮").pack(anchor=tk.W, pady=2)
        ttk.Checkbutton(preview_frame, text="示例复选框").pack(anchor=tk.W, pady=2)
        
        # 实时预览
        self.theme_mode_var.trace_add("write", self._update_theme_preview)
        self.theme_color_var.trace_add("write", self._update_theme_preview)

    def _create_advanced_settings(self):
        """创建高级设置页内容"""
        # 使用滚动框架
        canvas = tk.Canvas(self.advanced_frame)
        scrollbar = ttk.Scrollbar(self.advanced_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw", width=550)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # 缓存设置
        cache_frame = ttk.LabelFrame(scrollable_frame, text="缓存设置", padding="5")
        cache_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # 缓存大小限制
        cache_size_frame = ttk.Frame(cache_frame)
        cache_size_frame.pack(fill=tk.X, pady=2)
        ttk.Label(cache_size_frame, text="缓存大小限制:").pack(side=tk.LEFT)
        self.cache_size_var = tk.StringVar(value="1024")
        cache_entry = ttk.Entry(cache_size_frame, width=8, textvariable=self.cache_size_var)
        cache_entry.pack(side=tk.LEFT, padx=5)
        ttk.Label(cache_size_frame, text="MB").pack(side=tk.LEFT)
        
        # 清理缓存按钮
        ttk.Button(
            cache_frame,
            text="清理缓存",
            command=self._clear_cache
        ).pack(anchor=tk.W, pady=5)
        
        # 日志设置
        log_frame = ttk.LabelFrame(scrollable_frame, text="日志设置", padding="5")
        log_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # 日志级别
        log_level_frame = ttk.Frame(log_frame)
        log_level_frame.pack(fill=tk.X, pady=2)
        ttk.Label(log_level_frame, text="日志级别:").pack(side=tk.LEFT)
        self.log_level_var = tk.StringVar(value="INFO")
        level_combo = ttk.Combobox(
            log_level_frame,
            values=["DEBUG", "INFO", "WARNING", "ERROR"],
            textvariable=self.log_level_var,
            state='readonly',
            width=10
        )
        level_combo.pack(side=tk.LEFT, padx=5)
        
        # 布局滚动区域
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def _update_theme_preview(self, *args):
        """更新主题预览"""
        # TODO: 实现主题预览更新
        pass

    def _clear_cache(self):
        """清理缓存"""
        # TODO: 实现缓存清理
        pass

    def load_settings(self):
        """加载设置到UI"""
        settings = self.settings_manager.settings
        
        # 加载代理设置
        self.proxy_enabled_var.set(settings["proxy"]["enabled"])
        self.http_proxy_var.set(settings["proxy"]["http"])
        self.https_proxy_var.set(settings["proxy"]["https"])
        
        # 加载API设置
        self.api_enabled_var.set(settings["api"]["enabled"])
        self.api_port_var.set(str(settings["api"]["port"]))
        self.api_oss_var.set(settings["api"]["default_oss"])
        
        # 加载上传设置
        self.multipart_upload_var.set(settings["upload"]["multipart_enabled"])
        self.chunk_size_var.set(str(settings["upload"]["chunk_size"]))
        self.upload_workers_var.set(str(settings["upload"]["workers"]))
        
        # 加载下载设置
        self.multipart_download_var.set(settings["download"]["multipart_enabled"])
        self.download_chunk_size_var.set(str(settings["download"]["chunk_size"]))
        self.download_workers_var.set(str(settings["download"]["workers"]))
        
        # 加载默认设置
        self.default_oss_var.set(settings["default"]["oss_source"])
        
        # 加载列表显示设置
        self.list_size_var.set(str(settings["list"]["page_size"]))
        
        # 加载安全设置
        self.client_encryption_var.set(settings["security"]["client_encryption"])
        self.encryption_method_var.set(settings["security"]["encryption_method"])
        self.secure_transfer_var.set(settings["security"]["secure_transfer"])
        
        # 加载主题设置
        self.theme_mode_var.set(settings["theme"]["mode"])
        self.theme_color_var.set(settings["theme"]["color"])
        
        # 加载高级设置
        self.cache_size_var.set(str(settings["advanced"]["cache_size"]))
        self.log_level_var.set(settings["advanced"]["log_level"])
        
        # 更新UI状态
        self._on_proxy_toggle()
        self._on_api_toggle()
        self._on_encryption_toggle()
    
    def save_settings(self):
        """从UI保存设置"""
        try:
            # 验证数值输入
            self._validate_numeric_settings()
            
            settings = {
                "proxy": {
                    "enabled": self.proxy_enabled_var.get(),
                    "http": self.http_proxy_var.get(),
                    "https": self.https_proxy_var.get()
                },
                "api": {
                    "enabled": self.api_enabled_var.get(),
                    "port": int(self.api_port_var.get()),
                    "default_oss": self.api_oss_var.get()
                },
                "upload": {
                    "multipart_enabled": self.multipart_upload_var.get(),
                    "chunk_size": int(self.chunk_size_var.get()),
                    "workers": int(self.upload_workers_var.get())
                },
                "download": {
                    "multipart_enabled": self.multipart_download_var.get(),
                    "chunk_size": int(self.download_chunk_size_var.get()),
                    "workers": int(self.download_workers_var.get())
                },
                "default": {
                    "oss_source": self.default_oss_var.get()
                },
                "list": {
                    "page_size": int(self.list_size_var.get())
                },
                "security": {
                    "client_encryption": self.client_encryption_var.get(),
                    "encryption_method": self.encryption_method_var.get(),
                    "secure_transfer": self.secure_transfer_var.get()
                },
                "theme": {
                    "mode": self.theme_mode_var.get(),
                    "color": self.theme_color_var.get()
                },
                "advanced": {
                    "cache_size": int(self.cache_size_var.get()),
                    "log_level": self.log_level_var.get()
                }
            }
            
            return self.settings_manager.save_settings(settings)
            
        except ValueError as e:
            messagebox.showerror("错误", f"输入验证失败: {str(e)}")
            return False
    
    def _validate_numeric_settings(self):
        """验证数值设置项"""
        try:
            # API端口验证
            port = int(self.api_port_var.get())
            if not (1024 <= port <= 65535):
                raise ValueError("API端口必须在1024-65535之间")
            
            # 分片大小验证
            chunk_size = int(self.chunk_size_var.get())
            if not (1 <= chunk_size <= 1024):
                raise ValueError("分片大小必须在1-1024MB之间")
            
            dl_chunk_size = int(self.download_chunk_size_var.get())
            if not (1 <= dl_chunk_size <= 1024):
                raise ValueError("下载分片大小必须在1-1024MB之间")
            
            # 并发数验证
            workers = int(self.upload_workers_var.get())
            if not (1 <= workers <= 32):
                raise ValueError("上传并发数必须在1-32之间")
            
            dl_workers = int(self.download_workers_var.get())
            if not (1 <= dl_workers <= 32):
                raise ValueError("下载并发数必须在1-32之间")
            
            # 列表大小验证
            list_size = int(self.list_size_var.get())
            if not (100 <= list_size <= 10000):
                raise ValueError("列表大小必须在100-10000之间")
            
            # 缓存大小验证
            cache_size = int(self.cache_size_var.get())
            if not (100 <= cache_size <= 10240):
                raise ValueError("缓存大小必须在100-10240MB之间")
                
        except ValueError as e:
            if str(e).startswith("invalid literal for int()"):
                raise ValueError("请输入有效的数字")
            raise

    def load_oss_sources(self) -> dict:
        """从config.json加载OSS源配置"""
        try:
            return self.config_manager.load_config()
        except Exception as e:
            self.logger.error(f"Failed to load OSS sources: {e}")
            return {}