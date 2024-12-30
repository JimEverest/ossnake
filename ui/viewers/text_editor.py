import tkinter as tk
from tkinter import ttk
import logging
from typing import Optional, Callable
from .base_viewer import BaseViewer
import tkinter.messagebox as messagebox

class TextEditor(BaseViewer):
    """文本编辑器"""
    
    def __init__(self, parent, oss_client, object_name: str, mode: str = "edit"):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        self.oss_client = oss_client
        self.object_name = object_name
        self.mode = mode
        self.modified = False
        
        self.title(f"{'编辑' if mode == 'edit' else '预览'} - {object_name}")
        self.create_widgets()
        self.load_content()
        
        # 绑定关闭事件
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def create_widgets(self):
        """创建界面元素"""
        # 创建工具栏
        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X, padx=5, pady=5)
        
        # 添加编辑工具栏
        edit_frame = ttk.Frame(toolbar)
        edit_frame.pack(side=tk.LEFT, padx=5)
        
        # 撤销/重做按钮
        undo_btn = ttk.Button(
            edit_frame,
            text="撤销",
            command=self.undo,
            width=6
        )
        undo_btn.pack(side=tk.LEFT, padx=2)
        
        redo_btn = ttk.Button(
            edit_frame,
            text="重做",
            command=self.redo,
            width=6
        )
        redo_btn.pack(side=tk.LEFT, padx=2)
        
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=5)
        
        # 自动换行选项
        self.wrap_var = tk.BooleanVar(value=True)
        wrap_cb = ttk.Checkbutton(
            toolbar,
            text="自动换行",
            variable=self.wrap_var,
            command=self.toggle_wrap
        )
        wrap_cb.pack(side=tk.LEFT, padx=5)
        
        # 添加编码选择
        ttk.Label(toolbar, text="编码:").pack(side=tk.LEFT, padx=5)
        self.encoding_var = tk.StringVar(value='utf-8')
        self.encoding_combo = ttk.Combobox(
            toolbar,
            textvariable=self.encoding_var,
            values=['utf-8', 'gbk', 'gb2312', 'iso-8859-1'],
            width=10,
            state='readonly'
        )
        self.encoding_combo.pack(side=tk.LEFT, padx=5)
        self.encoding_combo.bind('<<ComboboxSelected>>', self.on_encoding_change)
        
        # 创建文本区域框架
        text_frame = ttk.Frame(self)
        text_frame.pack(expand=True, fill=tk.BOTH, padx=5, pady=5)
        
        # 创建行号文本框
        self.line_numbers = tk.Text(
            text_frame,
            width=4,
            padx=3,
            takefocus=0,
            border=0,
            background='lightgray',
            state='disabled'
        )
        self.line_numbers.pack(side=tk.LEFT, fill=tk.Y)
        
        # 创建主文本框
        self.text = tk.Text(
            text_frame,
            wrap=tk.WORD,
            undo=True,
            maxundo=100
        )
        # 配置搜索高亮标签
        self.text.tag_configure('search_highlight', background='yellow')
        
        # 同步行号和文本框的滚动
        self.text.bind('<KeyPress>', self.on_key_press)
        self.text.bind('<KeyRelease>', self.on_key_release)
        self.text.bind('<MouseWheel>', self.update_line_numbers)
        
        scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self.text.yview)
        self.text.configure(yscrollcommand=scrollbar.set)
        
        self.text.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 绑定标准的撤销/重做快捷键
        self.text.bind('<Control-z>', self.undo)
        self.text.bind('<Control-y>', self.redo)
        self.text.bind('<Control-Z>', self.redo)  # Shift+Ctrl+Z
        
        # 绑定文本修改事件
        self.text.bind('<<Modified>>', self.on_text_modified)
        
        # 如果是预览模式，设置为只读
        if self.mode == "view":
            self.text.config(state=tk.DISABLED)
        
        # 创建状态栏
        self.status_bar = ttk.Frame(self)
        self.status_bar.pack(fill=tk.X, padx=5, pady=2)
        
        # 位置信息
        self.position_label = ttk.Label(self.status_bar, text="行: 1, 列: 1")
        self.position_label.pack(side=tk.LEFT, padx=5)
        
        # 文件信息
        self.file_info_label = ttk.Label(self.status_bar, text="")
        self.file_info_label.pack(side=tk.LEFT, padx=5)
        
        # 编码信息
        self.encoding_label = ttk.Label(
            self.status_bar, 
            textvariable=self.encoding_var
        )
        self.encoding_label.pack(side=tk.RIGHT, padx=5)
        
        # 绑定光标移动事件
        self.text.bind('<KeyRelease>', self.update_status)
        self.text.bind('<Button-1>', self.update_status)
        self.text.bind('<ButtonRelease-1>', self.update_status)
        
        # 创建按钮框
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # 创建按钮
        if self.mode == "edit":
            self.save_btn = ttk.Button(
                btn_frame, 
                text="保存",
                command=self.save_content
            )
            self.save_btn.pack(side=tk.RIGHT, padx=5)
        
        self.close_btn = ttk.Button(
            btn_frame,
            text="关闭",
            command=self.destroy
        )
        self.close_btn.pack(side=tk.RIGHT)
        
        # 添加查找/替换按钮
        find_btn = ttk.Button(
            toolbar,
            text="查找",
            command=self.show_find_dialog
        )
        find_btn.pack(side=tk.LEFT, padx=5)
        
        # 在工具栏中添加统计按钮
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=5)
        
        stats_btn = ttk.Button(
            toolbar,
            text="统计",
            command=self.show_text_stats,
            width=6
        )
        stats_btn.pack(side=tk.LEFT, padx=2)
        
        # 在工具栏中添加格式化按钮
        if self.object_name.endswith('.py'):
            format_btn = ttk.Button(
                toolbar,
                text="格式化",
                command=self.format_python_code,
                width=6
            )
            format_btn.pack(side=tk.LEFT, padx=2)
    
    def load_content(self):
        """加载文件内容"""
        try:
            content = self.oss_client.get_object(self.object_name)
            
            # 尝试不同的编码方式
            encodings = ['utf-8', 'gbk', 'gb2312', 'iso-8859-1']
            text_content = None
            
            for encoding in encodings:
                try:
                    text_content = content.decode(encoding)
                    self.logger.info(f"Successfully decoded content with {encoding}")
                    break
                except UnicodeDecodeError:
                    continue
            
            if text_content is None:
                text_content = str(content)
                self.logger.warning("Failed to decode content with known encodings, displaying as binary")
            
            # 更新文本框内容
            if self.mode == "view":
                self.text.config(state=tk.NORMAL)
            self.text.delete(1.0, tk.END)
            self.text.insert(1.0, text_content)
            if self.mode == "view":
                self.text.config(state=tk.DISABLED)
            
            # 初始化行号
            self.update_line_numbers()
            
        except Exception as e:
            self.logger.error(f"Failed to load content: {str(e)}")
            self.show_error("加载失败", f"无法加载文件内容: {str(e)}")
    
    def save_content(self):
        """保存文件内容"""
        try:
            content = self.text.get(1.0, tk.END)
            # 尝试使用原始编码保存
            try:
                encoded_content = content.encode('utf-8')
            except UnicodeEncodeError:
                # 如果UTF-8编码失败，尝试使用GBK
                encoded_content = content.encode('gbk')
            
            self.oss_client.put_object(
                self.object_name,
                encoded_content,
                content_type='text/plain'
            )
            self.destroy()
        except Exception as e:
            self.logger.error(f"Failed to save content: {str(e)}")
            self.show_error("保存失败", f"无法保存文件: {str(e)}")
    
    def on_encoding_change(self, event=None):
        """处理编码改变"""
        try:
            content = self.oss_client.get_object(self.object_name)
            text_content = content.decode(self.encoding_var.get())
            
            if self.mode == "view":
                self.text.config(state=tk.NORMAL)
            self.text.delete(1.0, tk.END)
            self.text.insert(1.0, text_content)
            if self.mode == "view":
                self.text.config(state=tk.DISABLED)
            
        except UnicodeDecodeError:
            self.show_error("编码错误", f"无法使用 {self.encoding_var.get()} 编码解析文件内容")
        except Exception as e:
            self.logger.error(f"Failed to reload content with new encoding: {str(e)}")
            self.show_error("加载失败", f"重新加载文件内容失败: {str(e)}")
    
    def update_status(self, event=None):
        """更新状态栏信息"""
        try:
            # 更新光标位置
            pos = self.text.index(tk.INSERT)
            line, col = pos.split('.')
            self.position_label.config(text=f"行: {line}, 列: {int(col) + 1}")
            
            # 更新选中信息
            if self.text.tag_ranges(tk.SEL):
                sel_start = self.text.index(tk.SEL_FIRST)
                sel_end = self.text.index(tk.SEL_LAST)
                sel_text = self.text.get(sel_start, sel_end)
                self.file_info_label.config(text=f"已选择 {len(sel_text)} 个字符")
            else:
                # 显示总字符数
                total_chars = len(self.text.get(1.0, tk.END)) - 1  # 减去最后的换行符
                self.file_info_label.config(text=f"共 {total_chars} 个字符")
            
        except Exception as e:
            self.logger.error(f"Failed to update status: {str(e)}")
    
    def on_text_modified(self, event=None):
        """处理文本修改事件"""
        if not self.modified:
            self.modified = True
            self.title(f"*{'编辑' if self.mode == 'edit' else '预览'} - {self.object_name}")
    
    def on_closing(self):
        """处理窗口关闭事件"""
        if self.modified:
            answer = messagebox.askyesnocancel(
                "保存修改",
                "文件已修改，是否保存？"
            )
            if answer is None:  # 取消关闭
                return
            if answer:  # 保存并关闭
                self.save_content()
                return
        
        self.destroy() 
    
    def show_find_dialog(self):
        """显示查找对话框"""
        FindReplaceDialog(self)  # 直接创建对话框，不需要调用 show()
    
    def undo(self, event=None):
        """撤销操作"""
        try:
            self.text.edit_undo()
        except tk.TclError:  # 没有可撤销的操作
            pass
        return "break"  # 阻止事件继续传播
    
    def redo(self, event=None):
        """重做操作"""
        try:
            self.text.edit_redo()
        except tk.TclError:  # 没有可重做的操作
            pass
        return "break"
    
    def toggle_wrap(self):
        """切换自动换行"""
        if self.wrap_var.get():
            self.text.configure(wrap=tk.WORD)
        else:
            self.text.configure(wrap=tk.NONE)
    
    def update_line_numbers(self, event=None):
        """更新行号"""
        if not hasattr(self, 'line_numbers'):
            return
            
        # 获取文本框的行数
        final_index = self.text.index('end-1c')
        num_lines = int(final_index.split('.')[0])
        
        # 生成行号文本
        line_numbers_text = '\n'.join(str(i) for i in range(1, num_lines + 1))
        
        # 更新行号
        self.line_numbers.config(state='normal')
        self.line_numbers.delete('1.0', tk.END)
        self.line_numbers.insert('1.0', line_numbers_text)
        self.line_numbers.config(state='disabled')
        
        # 同步滚动位置
        self.line_numbers.yview_moveto(self.text.yview()[0])
    
    def on_key_press(self, event=None):
        """处理按键事件"""
        if event.keysym in ('Return', 'BackSpace', 'Delete'):
            self.update_line_numbers()
    
    def on_key_release(self, event=None):
        """处理按键释放事件"""
        if event.keysym in ('Return', 'BackSpace', 'Delete'):
            self.update_line_numbers()
    
    def show_text_stats(self):
        """显示文本统计信息"""
        content = self.text.get(1.0, tk.END)
        
        # 计算统计信息
        stats = {
            '字符数（含空格）': len(content),
            '字符数（不含空格）': len(content.replace(' ', '').replace('\n', '')),
            '单词数': len(content.split()),
            '行数': len(content.splitlines()),
            '空行数': content.count('\n\n'),
            '中文字符数': sum(1 for c in content if '\u4e00' <= c <= '\u9fff')
        }
        
        # 创建统计对话框
        dialog = tk.Toplevel(self)
        dialog.title("文本统计")
        dialog.geometry("300x200")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()
        
        # 显示统计信息
        for name, value in stats.items():
            frame = ttk.Frame(dialog)
            frame.pack(fill=tk.X, padx=10, pady=2)
            ttk.Label(frame, text=name).pack(side=tk.LEFT)
            ttk.Label(frame, text=str(value)).pack(side=tk.RIGHT)
        
        # 关闭按钮
        ttk.Button(
            dialog,
            text="关闭",
            command=dialog.destroy
        ).pack(pady=10)
    
    def format_python_code(self):
        """格式化Python代码"""
        try:
            import autopep8
            
            # 获取当前文本
            content = self.text.get(1.0, tk.END)
            
            # 格式化代码
            formatted_code = autopep8.fix_code(
                content,
                options={'aggressive': 1}
            )
            
            # 更新文本框
            self.text.delete(1.0, tk.END)
            self.text.insert(1.0, formatted_code)
            
            # 更新行号
            self.update_line_numbers()
            
            messagebox.showinfo("格式化", "代码格式化完成")
            
        except ImportError:
            messagebox.showerror("错误", "请先安装 autopep8: pip install autopep8")
        except Exception as e:
            self.logger.error(f"Code formatting failed: {str(e)}")
            messagebox.showerror("格式化失败", str(e))

class FindReplaceDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.title("查找/替换")
        self.geometry("400x300")  # 增加高度以确保显示所有内容
        self.resizable(False, False)
        
        # 使对话框模态
        self.transient(parent)
        self.grab_set()
        
        self.create_widgets()
        self.center_window()
    
    def center_window(self):
        """将窗口居中显示"""
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'+{x}+{y}')
    
    def create_widgets(self):
        """创建界面元素"""
        # 主框架添加padding
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 查找框
        find_frame = ttk.LabelFrame(main_frame, text="查找", padding="5")
        find_frame.pack(fill=tk.X, pady=(0, 5))
        
        self.find_var = tk.StringVar()
        self.find_entry = ttk.Entry(
            find_frame,
            textvariable=self.find_var,
            width=40
        )
        self.find_entry.pack(fill=tk.X, padx=5, pady=5)
        
        # 替换框
        replace_frame = ttk.LabelFrame(main_frame, text="替换为", padding="5")
        replace_frame.pack(fill=tk.X, pady=5)
        
        self.replace_var = tk.StringVar()
        self.replace_entry = ttk.Entry(
            replace_frame,
            textvariable=self.replace_var,
            width=40
        )
        self.replace_entry.pack(fill=tk.X, padx=5, pady=5)
        
        # 选项框
        options_frame = ttk.LabelFrame(main_frame, text="选项", padding="5")
        options_frame.pack(fill=tk.X, pady=5)
        
        # 添加选项
        options_inner_frame = ttk.Frame(options_frame)
        options_inner_frame.pack(padx=5, pady=5)
        
        self.case_sensitive = tk.BooleanVar()
        ttk.Checkbutton(
            options_inner_frame,
            text="区分大小写",
            variable=self.case_sensitive
        ).pack(side=tk.LEFT, padx=10)
        
        self.whole_word = tk.BooleanVar()
        ttk.Checkbutton(
            options_inner_frame,
            text="全词匹配",
            variable=self.whole_word
        ).pack(side=tk.LEFT, padx=10)
        
        # 按钮框
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))
        
        # 左侧按钮
        left_btn_frame = ttk.Frame(btn_frame)
        left_btn_frame.pack(side=tk.LEFT)
        
        ttk.Button(
            left_btn_frame,
            text="查找下一个",
            command=self.find_next,
            width=12
        ).pack(side=tk.LEFT, padx=2)
        
        ttk.Button(
            left_btn_frame,
            text="替换",
            command=self.replace,
            width=8
        ).pack(side=tk.LEFT, padx=2)
        
        ttk.Button(
            left_btn_frame,
            text="全部替换",
            command=self.replace_all,
            width=10
        ).pack(side=tk.LEFT, padx=2)
        
        # 右侧按钮
        ttk.Button(
            btn_frame,
            text="关闭",
            command=self.destroy,
            width=8
        ).pack(side=tk.RIGHT, padx=2)
        
        # 设置初始焦点
        self.find_entry.focus_set()
        
        # 绑定回车键
        self.bind('<Return>', lambda e: self.find_next())
        self.find_entry.bind('<Return>', lambda e: self.find_next())
        self.replace_entry.bind('<Return>', lambda e: self.replace())
    
    def find_next(self):
        """查找下一个匹配"""
        text = self.parent.text
        search_str = self.find_var.get()
        
        if not search_str:
            return
        
        # 清除之前的高亮
        text.tag_remove('search_highlight', '1.0', tk.END)
        
        # 获取当前位置
        current_pos = text.index(tk.INSERT)
        
        # 查找下一个匹配
        pos = text.search(search_str, current_pos, tk.END)
        if pos:
            # 高亮显示找到的文本
            end_pos = f"{pos}+{len(search_str)}c"
            text.tag_add('search_highlight', pos, end_pos)
            
            # 设置插入点并确保可见
            text.mark_set(tk.INSERT, end_pos)
            text.see(pos)
            
            # 选中文本
            text.tag_remove(tk.SEL, '1.0', tk.END)
            text.tag_add(tk.SEL, pos, end_pos)
        else:
            # 如果没找到，从头开始搜索
            pos = text.search(search_str, '1.0', current_pos)
            if pos:
                end_pos = f"{pos}+{len(search_str)}c"
                text.tag_add('search_highlight', pos, end_pos)
                text.mark_set(tk.INSERT, end_pos)
                text.see(pos)
                text.tag_remove(tk.SEL, '1.0', tk.END)
                text.tag_add(tk.SEL, pos, end_pos)
            else:
                messagebox.showinfo("查找", "找不到匹配内容")
    
    def replace(self):
        """替换当前选中的文本"""
        text = self.parent.text
        replace_str = self.replace_var.get()
        
        try:
            # 获取选中的文本范围
            sel_range = text.tag_ranges(tk.SEL)
            if sel_range:
                text.delete(sel_range[0], sel_range[1])
                text.insert(sel_range[0], replace_str)
                # 继续查找下一个
                self.find_next()
            else:
                # 如果没有选中的文本，先查找
                self.find_next()
        except Exception as e:
            self.parent.logger.error(f"Replace failed: {str(e)}")
    
    def replace_all(self):
        """替换所有匹配的文本"""
        text = self.parent.text
        search_str = self.find_var.get()
        replace_str = self.replace_var.get()
        
        if not search_str:
            return
        
        # 记录当前位置
        original_pos = text.index(tk.INSERT)
        
        # 从头开始替换
        count = 0
        text.mark_set(tk.INSERT, "1.0")
        
        while True:
            pos = text.search(search_str, tk.INSERT, tk.END)
            if not pos:
                break
            
            # 替换文本
            end_pos = f"{pos}+{len(search_str)}c"
            text.delete(pos, end_pos)
            text.insert(pos, replace_str)
            
            # 移动插入点到替换文本之后
            text.mark_set(tk.INSERT, f"{pos}+{len(replace_str)}c")
            count += 1
        
        # 恢复原始位置
        text.mark_set(tk.INSERT, original_pos)
        
        if count > 0:
            messagebox.showinfo("替换完成", f"共替换了 {count} 处")
        else:
            messagebox.showinfo("替换完成", "没有找到需要替换的内容") 