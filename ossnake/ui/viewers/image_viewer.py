import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import io
import logging
from .base_viewer import BaseViewer
import os
from ..components.loading_indicator import LoadingIndicator

class ImageViewer(BaseViewer):
    """图片查看器"""
    
    def __init__(self, parent, oss_client, object_name: str):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        self.oss_client = oss_client
        self.object_name = object_name
        self.zoom_level = 1.0  # 缩放级别
        
        # 设置初始窗口大小
        self.geometry("800x600")
        
        self.title(f"图片查看 - {object_name}")
        
        # 创建主框架
        self.main_frame = ttk.Frame(self)
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        self.create_widgets()
        # 延迟加载图片，等待窗口显示完成
        self.after(100, self.load_image)
    
    def create_widgets(self):
        """创建界面元素"""
        # 创建工具栏
        self.toolbar = ttk.Frame(self.main_frame)
        self.toolbar.pack(fill=tk.X, padx=5, pady=5)
        
        # 缩放按钮组
        zoom_frame = ttk.LabelFrame(self.toolbar, text="缩放")
        zoom_frame.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            zoom_frame,
            text="放大",
            command=self.zoom_in,
            width=6
        ).pack(side=tk.LEFT, padx=2)
        
        ttk.Button(
            zoom_frame,
            text="缩小",
            command=self.zoom_out,
            width=6
        ).pack(side=tk.LEFT, padx=2)
        
        ttk.Button(
            zoom_frame,
            text="适应",
            command=self.zoom_fit,
            width=6
        ).pack(side=tk.LEFT, padx=2)
        
        ttk.Button(
            zoom_frame,
            text="实际",
            command=self.zoom_actual,
            width=6
        ).pack(side=tk.LEFT, padx=2)
        
        # 显示缩放比例
        self.zoom_label = ttk.Label(zoom_frame, text="100%")
        self.zoom_label.pack(side=tk.LEFT, padx=5)
        
        # 旋转按钮组
        rotate_frame = ttk.LabelFrame(self.toolbar, text="旋转")
        rotate_frame.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            rotate_frame,
            text="左转",
            command=lambda: self.rotate(-90),
            width=6
        ).pack(side=tk.LEFT, padx=2)
        
        ttk.Button(
            rotate_frame,
            text="右转",
            command=lambda: self.rotate(90),
            width=6
        ).pack(side=tk.LEFT, padx=2)
        
        # 添加全屏按钮
        ttk.Separator(self.toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=5)
        
        ttk.Button(
            self.toolbar,
            text="全屏",
            command=self.toggle_fullscreen,
            width=6
        ).pack(side=tk.LEFT, padx=2)
        
        # 创建图片显示区域
        self.canvas = tk.Canvas(self.main_frame, bg='gray90')
        self.canvas.pack(expand=True, fill=tk.BOTH)
        
        # 创建状态栏
        self.status_frame = ttk.Frame(self.main_frame)
        self.status_frame.pack(fill=tk.X, padx=5, pady=2)
        
        # 图片信息标签
        self.info_label = ttk.Label(self.status_frame, text="")
        self.info_label.pack(side=tk.LEFT, padx=5)
        
        # 绑定事件
        self.canvas.bind('<ButtonPress-1>', self.start_move)
        self.canvas.bind('<B1-Motion>', self.move)
        self.canvas.bind('<MouseWheel>', self.mouse_wheel)
        self.bind('<Configure>', self.on_resize)
        
        # 绑定键盘事件
        self.bind('<Escape>', self.exit_fullscreen)
        self.bind('<F11>', self.toggle_fullscreen)
        
        # GIF动画控制
        self.is_playing = True
        self.current_frame = 0
        self.animation_speed = 100  # 默认动画速度(ms)
        
        # 如果是GIF，添加动画控制按钮
        if self.is_animated_gif():
            anim_frame = ttk.LabelFrame(self.toolbar, text="动画")
            anim_frame.pack(side=tk.LEFT, padx=5)
            
            self.play_btn = ttk.Button(
                anim_frame,
                text="暂停",
                command=self.toggle_animation,
                width=6
            )
            self.play_btn.pack(side=tk.LEFT, padx=2)
            
            # 速度控制
            ttk.Label(anim_frame, text="速度:").pack(side=tk.LEFT, padx=2)
            self.speed_var = tk.StringVar(value="100%")
            speed_combo = ttk.Combobox(
                anim_frame,
                textvariable=self.speed_var,
                values=["50%", "75%", "100%", "150%", "200%"],
                width=5,
                state='readonly'
            )
            speed_combo.pack(side=tk.LEFT, padx=2)
            speed_combo.bind('<<ComboboxSelected>>', self.update_animation_speed)
    
    def show_loading(self):
        """显示加载指示器"""
        # 先隐藏可能存在的旧指示器
        self.hide_loading()
        
        # 确保有效的窗口大小
        win_width = self.canvas.winfo_width()
        win_height = self.canvas.winfo_height()
        
        if win_width <= 1 or win_height <= 1:
            win_width = self.winfo_width()
            win_height = self.winfo_height()
        
        # 获取画布中心位置
        x = win_width // 2
        y = win_height // 2
        
        # 创建加载指示器
        self.loading = LoadingIndicator(self.canvas)
        
        # 在画布中央显示加载指示器
        self.loading_window = self.canvas.create_window(x, y, window=self.loading)
        
        # 确保更新显示
        self.canvas.update()

    def hide_loading(self):
        """隐藏加载指示器"""
        if hasattr(self, 'loading_window'):
            self.canvas.delete(self.loading_window)
        if hasattr(self, 'loading'):
            self.loading.destroy()
    
    def load_image(self):
        """加载图片"""
        try:
            # 显示加载指示器
            self.show_loading()
            
            # 获取图片数据
            self.image_data = self.oss_client.get_object(self.object_name)
            
            # 使用PIL打开图片
            self.original_image = Image.open(io.BytesIO(self.image_data))
            self.rotation_angle = 0  # 初始化旋转角度
            
            # 更新图片信息
            self.update_image_info()
            
            # 自动适应窗口大小
            self.zoom_fit()
            
            # 如果是GIF，开始动画
            if self.is_animated_gif():
                self.start_animation()
            
        except Exception as e:
            self.logger.error(f"Failed to load image: {str(e)}")
            self.show_error("加载失败", f"无法加载图片: {str(e)}")
        finally:
            # 隐藏加载指示器
            self.hide_loading()
    
    def update_image(self):
        """更新图片显示"""
        if not hasattr(self, 'original_image'):
            return
        
        try:
            # 计算缩放后的大小
            new_size = (
                int(self.original_image.width * self.zoom_level),
                int(self.original_image.height * self.zoom_level)
            )
            
            # 缩放图片
            resized = self.original_image.resize(new_size, Image.Resampling.LANCZOS)
            
            # 转换为PhotoImage
            self.photo = ImageTk.PhotoImage(resized)
            
            # 获取画布大小
            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()
            
            # 计算居中位置
            x = canvas_width // 2
            y = canvas_height // 2
            
            # 更新画布
            self.canvas.delete("all")
            self.canvas.create_image(x, y, image=self.photo)
            
            # 更新缩放比例显示
            self.zoom_label.config(text=f"{int(self.zoom_level * 100)}%")
            
        except Exception as e:
            self.logger.error(f"Failed to update image: {str(e)}")

    def zoom_in(self, event=None):
        """放大"""
        self.zoom_level *= 1.2
        self.update_image()

    def zoom_out(self, event=None):
        """缩小"""
        self.zoom_level /= 1.2
        self.update_image()

    def zoom_fit(self, event=None):
        """适应窗口"""
        if not hasattr(self, 'original_image'):
            return
        
        # 获取窗口和图片尺寸
        win_width = self.canvas.winfo_width()
        win_height = self.canvas.winfo_height()
        
        # 确保有效的窗口大小
        if win_width <= 1 or win_height <= 1:
            win_width = self.winfo_width() - 20  # 减去边距
            win_height = self.winfo_height() - 100  # 减去工具栏和状态栏高度
        
        img_width = self.original_image.width
        img_height = self.original_image.height
        
        # 计算缩放比例
        width_ratio = win_width / img_width
        height_ratio = win_height / img_height
        
        # 使用较小的比例以适应窗口
        self.zoom_level = min(width_ratio, height_ratio) * 0.9
        self.update_image()

    def zoom_actual(self, event=None):
        """实际大小"""
        self.zoom_level = 1.0
        self.update_image()

    def mouse_wheel(self, event):
        """鼠标滚轮缩放"""
        if event.delta > 0:
            self.zoom_in()
        else:
            self.zoom_out()

    def start_move(self, event):
        """开始拖动"""
        self.canvas.scan_mark(event.x, event.y)

    def move(self, event):
        """拖动图片"""
        self.canvas.scan_dragto(event.x, event.y, gain=1) 

    def on_resize(self, event):
        """处理窗口大小变化"""
        if event.widget == self:
            # 更新图片显示以适应新窗口大小
            self.update_image() 

    def update_image_info(self):
        """更新图片信息"""
        if not hasattr(self, 'original_image'):
            return
        
        try:
            # 获取图片信息
            width, height = self.original_image.size
            mode = self.original_image.mode
            format = self.original_image.format
            
            # 使用内存中的数据大小
            if hasattr(self, 'image_data'):
                size_str = self.format_size(len(self.image_data))
            else:
                size_str = "未知"
            
            # 更新信息显示
            info_text = f"尺寸: {width}x{height} | 格式: {format} | 模式: {mode} | 大小: {size_str}"
            self.info_label.config(text=info_text)
            
        except Exception as e:
            self.logger.error(f"Failed to update image info: {str(e)}")
            self.info_label.config(text="无法获取图片信息")

    def rotate(self, angle):
        """旋转图片
        Args:
            angle: 旋转角度（正数为顺时针，负数为逆时针）
        """
        if not hasattr(self, 'original_image'):
            return
        
        # 更新旋转角度
        self.rotation_angle = (self.rotation_angle + angle) % 360
        
        # 应用旋转
        rotated = self.original_image.rotate(
            -self.rotation_angle,  # PIL的旋转方向与我们相反
            expand=True,
            resample=Image.Resampling.BICUBIC
        )
        
        # 更新原始图片
        self.original_image = rotated
        
        # 更新显示
        self.update_image()
        self.update_image_info()

    def is_animated_gif(self):
        """检查是否是动画GIF"""
        return (hasattr(self, 'original_image') and 
                getattr(self.original_image, 'is_animated', False) and 
                self.original_image.format == 'GIF')

    def start_animation(self):
        """开始GIF动画"""
        if not self.is_animated_gif():
            return
        
        def update_frame():
            if not self.is_playing:
                return
            
            try:
                # 显示下一帧
                self.original_image.seek(self.current_frame)
                self.update_image()
                
                # 更新帧索引
                self.current_frame = (self.current_frame + 1) % self.original_image.n_frames
                
                # 继续动画
                self.after(self.animation_speed, update_frame)
                
            except Exception as e:
                self.logger.error(f"Animation error: {str(e)}")
        
        # 开始动画循环
        update_frame()

    def toggle_animation(self):
        """切换动画播放状态"""
        if not self.is_animated_gif():
            return
        
        self.is_playing = not self.is_playing
        self.play_btn.config(text="继续" if not self.is_playing else "暂停")
        
        if self.is_playing:
            self.start_animation()

    def update_animation_speed(self, event=None):
        """更新动画速度"""
        speed_text = self.speed_var.get().rstrip('%')
        speed_percent = float(speed_text) / 100
        self.animation_speed = int(100 / speed_percent)

    def toggle_fullscreen(self, event=None):
        """切换全屏显示"""
        state = self.attributes('-fullscreen')
        self.attributes('-fullscreen', not state)
        
        if not state:  # 进入全屏
            # 隐藏工具栏和状态栏
            self.toolbar.pack_forget()
            self.status_frame.pack_forget()
            # 确保画布填满整个窗口
            self.canvas.pack(expand=True, fill=tk.BOTH)
        else:  # 退出全屏
            # 恢复工具栏和状态栏
            self.toolbar.pack(in_=self.main_frame, fill=tk.X, padx=5, pady=5, side=tk.TOP)
            self.canvas.pack(in_=self.main_frame, expand=True, fill=tk.BOTH)
            self.status_frame.pack(in_=self.main_frame, fill=tk.X, padx=5, pady=2, side=tk.BOTTOM)
        
        # 更新图片显示
        self.update_image()

    def exit_fullscreen(self, event=None):
        """退出全屏"""
        if self.attributes('-fullscreen'):
            self.toggle_fullscreen()

    @staticmethod
    def format_size(size: int) -> str:
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB" 