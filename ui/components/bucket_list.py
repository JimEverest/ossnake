import tkinter as tk
from tkinter import ttk
import logging
import tkinter.messagebox as messagebox

class BucketList(ttk.Frame):
    """存储桶列表组件"""
    def __init__(self, parent, oss_client=None):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        self.oss_client = oss_client
        
        self.create_widgets()
        if self.oss_client:
            self.load_buckets()
    
    def create_widgets(self):
        """创建列表组件"""
        # 创建标题标签
        self.title_label = ttk.Label(self, text="存储桶列表", anchor=tk.W, font=('Helvetica', 10, 'bold'))
        self.title_label.pack(fill=tk.X, padx=5, pady=(0, 5))
        
        # 创建树形视图框架
        tree_frame = ttk.Frame(self)
        tree_frame.pack(expand=True, fill=tk.BOTH)
        
        # 创建Treeview用于显示存储桶
        self.tree = ttk.Treeview(
            tree_frame,
            columns=('name', 'region', 'objects'),
            show='headings',
            selectmode='browse'
        )
        
        # 设置列
        self.tree.heading('name', text='名称')
        self.tree.heading('region', text='区域')
        self.tree.heading('objects', text='对象数')
        
        self.tree.column('name', width=150, minwidth=100)
        self.tree.column('region', width=100, minwidth=80)
        self.tree.column('objects', width=70, minwidth=50)
        
        # 添加滚动条
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        # 布局
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 绑定选择事件
        self.tree.bind('<<TreeviewSelect>>', self.on_select)
    
    def load_buckets(self):
        """加载存储桶列表"""
        try:
            # 清空现有项目
            for item in self.tree.get_children():
                self.tree.delete(item)
            
            if not self.oss_client:
                self.logger.warning("No OSS client configured")
                return
            
            # 获取并显示存储桶列表
            # 由于目前我们只有一个bucket配置，直接显示当前bucket
            config = self.oss_client.config
            self.tree.insert('', tk.END, values=(
                config.bucket_name,
                config.region or '-',
                '0'  # 对象数暂时显示为0
            ))
            
            self.logger.info(f"Loaded bucket: {config.bucket_name}")
            
        except Exception as e:
            self.logger.error(f"Failed to load buckets: {str(e)}")
            messagebox.showerror("错误", f"加载存储桶失败: {str(e)}")
    
    def on_select(self, event):
        """处理选择事件"""
        selection = self.tree.selection()
        if selection:
            item = self.tree.item(selection[0])
            bucket_name = item['values'][0]
            self.logger.info(f"Selected bucket: {bucket_name}")
            # 这里可以触发bucket选择事件
    
    def set_oss_client(self, client):
        """设置OSS客户端"""
        self.oss_client = client
        self.load_buckets() 