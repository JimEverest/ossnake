# ui/settings.py
# 实现一个设置窗口，用于添加或编辑OSS源的配置信息。
import tkinter as tk
from tkinter import ttk
from tkinter import messagebox

class SettingsWindow(tk.Toplevel):
    def __init__(self, parent, config_manager, refresh_callback):
        super().__init__(parent)
        self.title("配置OSS源")
        self.geometry("400x300")
        self.config_manager = config_manager
        self.refresh_callback = refresh_callback
        
        self.create_widgets()
    
    def create_widgets(self):
        # 示例：添加AWS S3源
        frame = ttk.Frame(self, padding=10)
        frame.pack(expand=True, fill=tk.BOTH)
        
        ttk.Label(frame, text="名称:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.name_entry = ttk.Entry(frame)
        self.name_entry.grid(row=0, column=1, pady=5)
        
        ttk.Label(frame, text="提供商:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.provider_var = tk.StringVar()
        self.provider_combo = ttk.Combobox(frame, textvariable=self.provider_var, state="readonly")
        self.provider_combo['values'] = ("aws_s3", "aliyun_oss", "minio_oss")
        self.provider_combo.grid(row=1, column=1, pady=5)
        self.provider_combo.current(0)
        
        ttk.Label(frame, text="Access Key:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.access_key_entry = ttk.Entry(frame)
        self.access_key_entry.grid(row=2, column=1, pady=5)
        
        ttk.Label(frame, text="Secret Key:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.secret_key_entry = ttk.Entry(frame, show="*")
        self.secret_key_entry.grid(row=3, column=1, pady=5)
        
        ttk.Label(frame, text="Region:").grid(row=4, column=0, sticky=tk.W, pady=5)
        self.region_entry = ttk.Entry(frame)
        self.region_entry.grid(row=4, column=1, pady=5)
        
        ttk.Label(frame, text="Endpoint (可选):").grid(row=5, column=0, sticky=tk.W, pady=5)
        self.endpoint_entry = ttk.Entry(frame)
        self.endpoint_entry.grid(row=5, column=1, pady=5)
        
        ttk.Label(frame, text="Proxy (可选):").grid(row=6, column=0, sticky=tk.W, pady=5)
        self.proxy_entry = ttk.Entry(frame)
        self.proxy_entry.grid(row=6, column=1, pady=5)
        
        ttk.Button(frame, text="保存", command=self.save_config).grid(row=7, column=0, columnspan=2, pady=10)
    
    def save_config(self):
        name = self.name_entry.get().strip()
        provider = self.provider_var.get()
        access_key = self.access_key_entry.get().strip()
        secret_key = self.secret_key_entry.get().strip()
        region = self.region_entry.get().strip()
        endpoint = self.endpoint_entry.get().strip()
        proxy = self.proxy_entry.get().strip()
        
        if not name or not access_key or not secret_key or not region:
            messagebox.showerror("错误", "请填写所有必填字段")
            return
        
        config = {
            "provider": provider,
            "access_key": access_key,
            "secret_key": secret_key,
            "region": region,
            "endpoint": endpoint if endpoint else None,
            "proxy": proxy if proxy else None
        }
        
        try:
            self.config_manager.add_client(name, config)
            messagebox.showinfo("成功", "OSS源配置已保存")
            self.refresh_callback()
            self.destroy()
        except Exception as e:
            messagebox.showerror("错误", f"保存配置失败: {str(e)}")
