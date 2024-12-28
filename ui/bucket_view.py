# ui/bucket_view.py
# 使用ttk.Treeview展示存储桶中的文件和文件夹，支持浏览、搜索、上传、下载等操作
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from threading import Thread
from PIL import Image, ImageTk
import io
import tkinterdnd2 as tkdnd
from .progress_window import ProgressWindow  # Import ProgressWindow
from .file_preview import FilePreviewWindow # Import FilePreviewWindow

class BucketView(ttk.Frame):
    def __init__(self, parent, oss_client):
        super().__init__(parent)
        self.oss_client = oss_client
        self.create_widgets()
        self.load_buckets()
        self.bind_clipboard() # Initialize clipboard binding
    
    def create_widgets(self):
        # 左侧列表显示存储桶
        self.bucket_list = tk.Listbox(self, width=30)
        self.bucket_list.pack(side=tk.LEFT, fill=tk.Y)
        self.bucket_list.bind('<<ListboxSelect>>', self.on_bucket_select)
        
        # 右侧Treeview显示对象
        self.tree = ttk.Treeview(self, columns=('Name', 'Type', 'Size', 'Last Modified'), show='headings')
        self.tree.heading('Name', text='名称')
        self.tree.heading('Type', text='类型')
        self.tree.heading('Size', text='大小')
        self.tree.heading('Last Modified', text='最后修改时间')
        self.tree.pack(side=tk.RIGHT, expand=True, fill=tk.BOTH)
        self.tree.bind('<Double-1>', self.on_item_double_click)
        
        # 右键菜单
        self.tree_menu = tk.Menu(self, tearoff=0)
        self.tree_menu.add_command(label="下载", command=self.download_selected)
        self.tree_menu.add_command(label="删除", command=self.delete_selected)
        self.tree_menu.add_command(label="重命名", command=self.rename_selected)
        self.tree_menu.add_command(label="预览", command=self.preview_selected)
        self.tree.bind("<Button-3>", self.show_tree_menu)

        # 搜索栏
        search_frame = ttk.Frame(self)
        search_frame.pack(side=tk.TOP, fill=tk.X)
        
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        search_entry.pack(side=tk.LEFT, padx=5, pady=5, expand=True, fill=tk.X)
        
        search_button = ttk.Button(search_frame, text="搜索", command=self.search_objects)
        search_button.pack(side=tk.LEFT, padx=5, pady=5)

        # 绑定拖拽事件
        self.tree.drop_target_register(tkdnd.DND_FILES)
        self.tree.dnd_bind('<Drop>', self.on_drop)

    def on_drop(self, event):
        files = self.tree.tk.splitlist(event.data)
        for file_path in files:
            object_name = os.path.basename(file_path)
            Thread(target=self._upload_thread, args=(file_path, object_name)).start()
    
    def _upload_thread(self, local_file, object_name):
        try:
            # 创建进度窗口
            progress_win = ProgressWindow(self, f"上传 {object_name}")
            def progress_callback(transferred, total):
                progress_win.update_progress(transferred, total)
            self.oss_client.upload_file(local_file, object_name, progress_callback=progress_callback)
            progress_win.close()
            self.load_objects(self.oss_client.config.bucket_name)
            messagebox.showinfo("成功", f"上传成功: {object_name}")
        except Exception as e:
            messagebox.showerror("错误", f"上传失败: {str(e)}")

    def load_buckets(self):
        try:
            buckets = self.oss_client.list_buckets()
            self.bucket_list.delete(0, tk.END)
            for bucket in buckets:
                self.bucket_list.insert(tk.END, bucket['name'])
        except Exception as e:
            messagebox.showerror("错误", f"加载存储桶失败: {str(e)}")
    
    def on_bucket_select(self, event):
        selection = self.bucket_list.curselection()
        if selection:
            bucket_name = self.bucket_list.get(selection[0])
            self.load_objects(bucket_name)
    
    def load_objects(self, bucket_name):
        # 切换到选中的存储桶
        self.oss_client.config.bucket_name = bucket_name
        Thread(target=self._load_objects_thread).start()
    
    def _load_objects_thread(self):
        try:
            objects = self.oss_client.list_objects()
            self.tree.delete(*self.tree.get_children())
            for obj in objects:
                self.tree.insert('', 'end', values=(
                    obj['name'],
                    obj['type'],
                    obj['size'],
                    obj['last_modified']
                ))
        except Exception as e:
            messagebox.showerror("错误", f"加载对象失败: {str(e)}")
    
    def on_item_double_click(self, event):
        selected = self.tree.focus()
        if not selected:
            return
        item = self.tree.item(selected)
        obj_name, obj_type = item['values'][0], item['values'][1]
        if obj_type == 'folder':
            self.load_objects(obj_name)
        else:
            self.preview_file(obj_name)
    
    def show_tree_menu(self, event):
        try:
            self.tree_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.tree_menu.grab_release()
    
    def download_selected(self):
        selected = self.tree.focus()
        if not selected:
            return
        item = self.tree.item(selected)
        obj = item['values'][0]
        local_path = filedialog.askdirectory()
        if local_path:
            Thread(target=self._download_thread, args=(obj, local_path)).start()
    
    def _download_thread(self, object_name, local_path):
        try:
            self.oss_client.download_file(object_name, f"{local_path}/{object_name}")
            messagebox.showinfo("成功", f"下载成功: {object_name}")
        except Exception as e:
            messagebox.showerror("错误", f"下载失败: {str(e)}")
    
    def delete_selected(self):
        selected = self.tree.focus()
        if not selected:
            return
        item = self.tree.item(selected)
        obj = item['values'][0]
        confirm = messagebox.askyesno("确认", f"确定要删除 {obj} 吗？")
        if confirm:
            Thread(target=self._delete_thread, args=(obj,)).start()
    
    def _delete_thread(self, object_name):
        try:
            self.oss_client.delete_file(object_name)
            self.load_objects(self.oss_client.config.bucket_name)
            messagebox.showinfo("成功", f"删除成功: {object_name}")
        except Exception as e:
            messagebox.showerror("错误", f"删除失败: {str(e)}")
    
    def rename_selected(self):
        selected = self.tree.focus()
        if not selected:
            return
        item = self.tree.item(selected)
        obj = item['values'][0]
        new_name = simpledialog.askstring("重命名", f"输入新的名称 for {obj}:")
        if new_name:
            Thread(target=self._rename_thread, args=(obj, new_name)).start()
    
    def _rename_thread(self, source, target):
        try:
            self.oss_client.rename_object(source, target)
            self.load_objects(self.oss_client.config.bucket_name)
            messagebox.showinfo("成功", f"重命名成功: {source} -> {target}")
        except Exception as e:
            messagebox.showerror("错误", f"重命名失败: {str(e)}")
    
    def preview_selected(self):
        selected = self.tree.focus()
        if not selected:
            return
        item = self.tree.item(selected)
        obj = item['values'][0]
        Thread(target=self._preview_thread, args=(obj,)).start()
    
    def _preview_thread(self, object_name):
        try:
            presigned_url = self.oss_client.get_presigned_url(object_name)
            preview_window = FilePreviewWindow(self, presigned_url)
            preview_window.mainloop()
        except Exception as e:
            messagebox.showerror("错误", f"预览失败: {str(e)}")

    def search_objects(self):
        query = self.search_var.get().strip()
        if not query:
            messagebox.showwarning("警告", "请输入搜索关键词")
            return
        Thread(target=self._search_thread, args=(query,)).start()
    
    def _search_thread(self, query):
        try:
            objects = self.oss_client.list_objects(recursive=True)
            filtered = [obj for obj in objects if query in obj['name']]
            self.tree.delete(*self.tree.get_children())
            for obj in filtered:
                self.tree.insert('', 'end', values=(
                    obj['name'],
                    obj['type'],
                    obj['size'],
                    obj['last_modified']
                ))
        except Exception as e:
            messagebox.showerror("错误", f"搜索失败: {str(e)}")

            
    def bind_clipboard(self):
        self.bind("<Control-v>", self.paste_from_clipboard)
    
    def paste_from_clipboard(self, event):
        try:
            files = self.clipboard_get().split()
            for file_path in files:
                if os.path.isfile(file_path):
                    object_name = os.path.basename(file_path)
                    Thread(target=self._upload_thread, args=(file_path, object_name)).start()
        except Exception as e:
            messagebox.showerror("错误", f"粘贴上传失败: {str(e)}")