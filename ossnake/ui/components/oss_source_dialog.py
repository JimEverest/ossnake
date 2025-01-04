import tkinter as tk
from tkinter import ttk, messagebox
import logging
from ossnake.driver.types import OSSConfig

class OSSSourceDialog(tk.Toplevel):
    """OSS源配置对话框"""
    
    def __init__(self, parent, config_manager, source_data=None):
        """
        初始化对话框
        Args:
            parent: 父窗口
            config_manager: 配置管理器
            source_data: 现有源数据(用于编辑模式)
        """
        super().__init__(parent)
        self.parent = parent
        self.config_manager = config_manager
        self.source_data = source_data
        self.logger = logging.getLogger(__name__)
        
        # 设置窗口
        self.title("添加OSS源" if not source_data else "编辑OSS源")
        self.geometry("500x400")
        self.resizable(False, False)
        
        # 设置模态
        self.transient(parent)
        self.grab_set()
        
        # 创建界面
        self.create_widgets()
        
        # 如果是编辑模式，填充现有数据
        if source_data:
            self.load_source_data()
        
        # 居中显示
        self.center_window()
    
    def create_widgets(self):
        """创建界面元素"""
        # 主框架
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 基本信息
        basic_frame = ttk.LabelFrame(main_frame, text="基本信息", padding="5")
        basic_frame.pack(fill=tk.X, pady=(0, 10))
        
        # OSS源名称
        name_frame = ttk.Frame(basic_frame)
        name_frame.pack(fill=tk.X, pady=2)
        ttk.Label(name_frame, text="名称:").pack(side=tk.LEFT)
        self.name_var = tk.StringVar()
        self.name_entry = ttk.Entry(name_frame, textvariable=self.name_var)
        self.name_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        # OSS类型
        type_frame = ttk.Frame(basic_frame)
        type_frame.pack(fill=tk.X, pady=2)
        ttk.Label(type_frame, text="类型:").pack(side=tk.LEFT)
        self.type_var = tk.StringVar()
        self.type_combo = ttk.Combobox(
            type_frame, 
            textvariable=self.type_var,
            values=["aws", "aliyun", "minio"],
            state="readonly"
        )
        self.type_combo.pack(side=tk.LEFT, padx=5)
        self.type_combo.bind('<<ComboboxSelected>>', self.on_type_change)
        
        # 认证信息
        auth_frame = ttk.LabelFrame(main_frame, text="认证信息", padding="5")
        auth_frame.pack(fill=tk.X, pady=5)
        
        # Access Key
        ak_frame = ttk.Frame(auth_frame)
        ak_frame.pack(fill=tk.X, pady=2)
        ttk.Label(ak_frame, text="Access Key:").pack(side=tk.LEFT)
        self.ak_var = tk.StringVar()
        self.ak_entry = ttk.Entry(ak_frame, textvariable=self.ak_var)
        self.ak_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        # Secret Key
        sk_frame = ttk.Frame(auth_frame)
        sk_frame.pack(fill=tk.X, pady=2)
        ttk.Label(sk_frame, text="Secret Key:").pack(side=tk.LEFT)
        self.sk_var = tk.StringVar()
        self.sk_entry = ttk.Entry(sk_frame, textvariable=self.sk_var, show="*")
        self.sk_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        # 连接信息
        conn_frame = ttk.LabelFrame(main_frame, text="连接信息", padding="5")
        conn_frame.pack(fill=tk.X, pady=5)
        
        # Region
        region_frame = ttk.Frame(conn_frame)
        region_frame.pack(fill=tk.X, pady=2)
        ttk.Label(region_frame, text="区域:").pack(side=tk.LEFT)
        self.region_var = tk.StringVar()
        self.region_entry = ttk.Entry(region_frame, textvariable=self.region_var)
        self.region_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        # Endpoint
        endpoint_frame = ttk.Frame(conn_frame)
        endpoint_frame.pack(fill=tk.X, pady=2)
        ttk.Label(endpoint_frame, text="Endpoint:").pack(side=tk.LEFT)
        self.endpoint_var = tk.StringVar()
        self.endpoint_entry = ttk.Entry(endpoint_frame, textvariable=self.endpoint_var)
        self.endpoint_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        # Bucket
        bucket_frame = ttk.Frame(conn_frame)
        bucket_frame.pack(fill=tk.X, pady=2)
        ttk.Label(bucket_frame, text="Bucket:").pack(side=tk.LEFT)
        self.bucket_var = tk.StringVar()
        self.bucket_entry = ttk.Entry(bucket_frame, textvariable=self.bucket_var)
        self.bucket_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        # 添加 Secure 选项
        secure_frame = ttk.Frame(conn_frame)
        secure_frame.pack(fill=tk.X, pady=2)
        self.secure_var = tk.BooleanVar(value=True)  # 默认启用
        self.secure_check = ttk.Checkbutton(
            secure_frame,
            text="启用HTTPS安全连接",
            variable=self.secure_var,
            command=self._on_secure_toggle
        )
        self.secure_check.pack(side=tk.LEFT)
        
        # 按钮
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=10)
        
        ttk.Button(
            btn_frame,
            text="测试连接",
            command=self.test_connection,
            width=10
        ).pack(side=tk.LEFT)
        
        ttk.Button(
            btn_frame,
            text="确定",
            command=self.save_source,
            width=10
        ).pack(side=tk.RIGHT, padx=(5, 0))
        
        ttk.Button(
            btn_frame,
            text="取消",
            command=self.destroy,
            width=10
        ).pack(side=tk.RIGHT)
    
    def center_window(self):
        """居中显示窗口"""
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'{width}x{height}+{x}+{y}')
    
    def on_type_change(self, event=None):
        """处理OSS类型变化"""
        oss_type = self.type_var.get()
        if oss_type == "minio":
            self.endpoint_entry.config(state="normal")
            self.region_entry.config(state="disabled")
        else:
            self.endpoint_entry.config(state="normal" if oss_type == "aliyun" else "disabled")
            self.region_entry.config(state="normal")
    
    def load_source_data(self):
        """加载现有源数据"""
        if not self.source_data:
            return
            
        name, config = self.source_data
        self.name_var.set(name)
        self.type_var.set(config.get('provider', ''))
        self.ak_var.set(config.get('access_key', ''))
        self.sk_var.set(config.get('secret_key', ''))
        self.region_var.set(config.get('region', ''))
        self.endpoint_var.set(config.get('endpoint', ''))
        self.bucket_var.set(config.get('bucket_name', ''))
        self.secure_var.set(config.get('secure', True))  # 加载secure设置
        
        # 更新界面状态
        self.on_type_change()
        
        # 禁用名称输入(编辑模式下不允许修改名称)
        self.name_entry.config(state="disabled")
    
    def test_connection(self):
        """测试连接"""
        config = self._get_config()
        if not config:
            return
            
        try:
            # 将字典转换为 OSSConfig 对象
            config_obj = OSSConfig(**config)
            oss_type = config['provider']
            
            try:
                # 根据不同的 OSS 类型进行测试
                if oss_type == 'aliyun':
                    # 阿里云特殊处理
                    import oss2  # 确保已导入 oss2
                    auth = oss2.Auth(config['access_key'], config['secret_key'])
                    endpoint = f"https://oss-{config['region']}.aliyuncs.com"
                    bucket = oss2.Bucket(auth, endpoint, config['bucket_name'])
                    # 测试连接
                    bucket.list_objects(max_keys=1)
                else:
                    # AWS 和 MinIO 使用通用方式
                    client_class = self.config_manager._get_client_class(config['provider'])
                    client = client_class(config_obj)
                    client.list_buckets()
                    
                messagebox.showinfo("成功", "连接测试成功")
                
            except oss2.exceptions.OssError as e:
                raise Exception(f"阿里云OSS错误: {str(e)}")
            except Exception as e:
                raise
                
        except Exception as e:
            self.logger.error(f"Connection test failed: {str(e)}")
            messagebox.showerror("错误", f"连接测试失败: {str(e)}")
    
    def _get_config(self):
        """获取配置数据"""
        try:
            name = self.name_var.get().strip()
            if not name:
                raise ValueError("请输入OSS源名称")
                
            oss_type = self.type_var.get()
            if not oss_type:
                raise ValueError("请选择OSS类型")
                
            config = {
                'provider': oss_type,
                'access_key': self.ak_var.get().strip(),
                'secret_key': self.sk_var.get().strip(),
                'region': self.region_var.get().strip(),
                'endpoint': self.endpoint_var.get().strip(),
                'bucket_name': self.bucket_var.get().strip(),
                'secure': self.secure_var.get()  # 添加secure设置
            }
            
            # MinIO 特殊处理
            if oss_type == "minio":
                endpoint = config['endpoint']
                if endpoint:
                    # 确保endpoint不包含协议前缀
                    if endpoint.startswith('http://') or endpoint.startswith('https://'):
                        config['endpoint'] = endpoint.split('://', 1)[1]
            
            # 验证必填字段
            if not config['access_key']:
                raise ValueError("请输入Access Key")
            if not config['secret_key']:
                raise ValueError("请输入Secret Key")
            if not config['bucket_name']:
                raise ValueError("请输入Bucket名称")
                
            # 根据类型验证特定字段
            if oss_type == "minio":
                if not config['endpoint']:
                    raise ValueError("MinIO需要设置Endpoint")
            elif oss_type == "aliyun":
                if not config['region']:
                    raise ValueError("阿里云OSS需要设置区域")
                # 阿里云特殊处理
                if not config['endpoint']:
                    config['endpoint'] = f"oss-{config['region']}.aliyuncs.com"
            elif oss_type == "aws":
                if not config['region']:
                    raise ValueError("AWS S3需要设置区域")
            
            return config
            
        except ValueError as e:
            messagebox.showerror("错误", str(e))
            return None
    
    def save_source(self):
        """保存OSS源配置"""
        try:
            # 获取表单数据并验证
            config = self._get_config()
            if not config:  # 如果验证失败，_get_config 会返回 None
                return
            
            # 获取名称
            name = self.name_var.get().strip()
            
            # 如果是编辑模式，先删除旧的
            if self.source_data:  # 使用 source_data 判断是否是编辑模式
                old_name = self.source_data[0]  # 获取原来的名称
                self.config_manager.remove_client(old_name)
            
            # 添加新配置
            self.config_manager.add_client(name, config)
            
            # 刷新父窗口的列表
            self.parent._load_oss_sources()
            
            # 显示成功提示
            messagebox.showinfo("成功", f"OSS源 '{name}' 保存成功")
            
            # 关闭窗口
            self.destroy()
            
        except Exception as e:
            self.logger.error(f"Failed to save OSS source: {str(e)}")
            messagebox.showerror("错误", f"保存失败: {str(e)}")
    
    def _on_secure_toggle(self):
        """处理安全连接切换"""
        is_secure = self.secure_var.get()
        oss_type = self.type_var.get()
        
        # 根据不同的OSS类型处理endpoint
        if oss_type == "minio":
            endpoint = self.endpoint_var.get().strip()
            if endpoint:
                # 移除现有的协议前缀
                if endpoint.startswith('http://') or endpoint.startswith('https://'):
                    endpoint = endpoint.split('://', 1)[1]
                # 添加新的协议前缀
                self.endpoint_var.set(f"{'https' if is_secure else 'http'}://{endpoint}") 