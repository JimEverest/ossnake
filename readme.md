# OSS Explorer - 统一对象存储浏览器

## 1. 项目背景

OSS Explorer 是一个跨平台的对象存储服务浏览器,旨在提供类似本地文件资源管理器的使用体验。主要特性:

- 支持多种对象存储服务(Amazon S3、阿里云OSS、MinIO)
- 提供直观的图形界面,支持文件预览
- 支持拖拽上传下载
- 支持剪贴板操作
- 支持文件搜索和加密
- 支持代理设置
- 支持多账户配置和切换

## 2. 技术方案

### 2.1 技术栈
- 后端: Python 3.8+
- GUI: Tkinter
- 存储SDK: boto3(AWS)、oss2(阿里云)、minio-py(MinIO)
- 测试: unittest
- 文档: Markdown

### 2.2 核心功能
1. 文件操作
   - 上传/下载(支持文件夹)
   - 拖拽操作
   - 复制/移动/删除
   - 搜索功能

2. 预览功能
   - 文本文件
   - 图片(支持缩略图)
   - JSON格式化
   - 音视频流式播放

3. 高级特性
   - 客户端加密
   - 代理支持
   - 多账户管理
   - 断点续传

## 3. 系统架构

### 3.1 整体架构
```
ossnake/
├── driver/          # 存储服务驱动
│   ├── base_oss.py       # 基础抽象类
│   ├── oss_ali.py        # 阿里云实现
│   ├── aws_s3.py         # AWS实现
│   ├── minio_client.py   # MinIO实现
│   └── transfer_manager.py # 传输管理
├── ui/             # 用户界面
│   ├── explorer.py      # 主窗口
│   ├── preview/        # 预览组件
│   └── widgets/        # 通用组件
└── utils/          # 工具函数
```

### 3.2 模块职责

#### Driver层
- 提供统一的存储操作接口
- 处理文件传输和进度
- 管理认证和配置
- 错误处理和重试

#### UI层
- 提供文件浏览界面
- 实现预览功能
- 处理用户交互
- 显示传输进度

#### Utils层
- 提供通用工具函数
- 处理配置管理
- 实现缓存机制
- 日志管理

## 4. 存储功能实现

### 4.1 统一接口
所有存储服务都实现了以下核心功能:
- 基础文件操作(上传、下载、删除)
- 流式传输(支持大文件和媒体流)
- 分片上传(支持断点续传)
- 文件夹操作
- URL生成(临时和永久)
- 代理支持

详细功能列表和实现状态请参考: [功能实现状态](./docs/features.md)

### 4.2 特色功能
1. 智能传输管理
   - 自动选择传输方式
   - 动态调整并发数
   - 支持断点续传
   - 传输速度控制

2. 高级操作支持
   - 批量操作
   - 文件夹同步
   - 增量更新
   - 客户端加密

## 5. 测试覆盖

项目采用全面的测试策略,包括:
- 单元测试
- 集成测试
- 端到端测试
- 性能测试

详细的测试覆盖分析请参考: [测试覆盖分析](./test_all.md)

## 6. UI实现指南

### 6.1 设计原则
1. 简洁直观
   - 类Windows资源管理器的布局
   - 清晰的视觉层次
   - 响应式设计

2. 易用性
   - 支持拖拽操作
   - 快捷键支持
   - 右键菜单
   - 进度显示

3. 性能
   - 异步加载
   - 虚拟列表
   - 缓存机制

### 6.2 核心组件

1. 主窗口 (explorer.py)
```python
class Explorer(tk.Tk):
    def __init__(self):
        self.tree_view = FileTreeView()  # 文件树
        self.list_view = FileListView()  # 文件列表
        self.preview_panel = PreviewPanel()  # 预览面板
        self.status_bar = StatusBar()  # 状态栏
```

2. 预览组件 (preview/)
- 文本预览器
- 图片预览器
- 媒体播放器
- JSON查看器

3. 通用组件 (widgets/)
- 进度条
- 文件图标
- 右键菜单
- 对话框

### 6.3 实现建议

1. 文件操作
```python
def handle_drag_drop(self, event):
    """处理拖拽事件"""
    files = self.get_drag_data(event)
    self.start_upload(files)
```

2. 预览功能
```python
def preview_file(self, file_info):
    """根据文件类型选择预览器"""
    preview = self.get_preview_handler(file_info.type)
    preview.show(file_info)
```

3. 进度显示
```python
def update_progress(self, transferred, total):
    """更新进度条和状态"""
    self.progress_bar.update(transferred/total)
    self.status_bar.set_status(f"{transferred}/{total}")
```

## 7. 开发建议

### 7.1 环境设置
1. Python环境
   - 使用虚拟环境
   - 安装依赖包
   - 配置开发工具

2. 测试配置
   - 准备测试账号
   - 设置测试数据
   - 配置代理(如需)

### 7.2 开发流程
1. 功能开发
   - 先实现核心功能
   - 添加必要测试
   - 进行代码审查
   - 合并到主分支

2. UI开发
   - 实现基础布局
   - 添加交互功能
   - 优化用户体验
   - 进行UI测试

### 7.3 注意事项
1. 性能优化
   - 使用异步操作
   - 实现缓存机制
   - 控制内存使用
   - 优化网络请求

2. 错误处理
   - 优雅处理异常
   - 提供错误反馈
   - 支持操作重试
   - 保存错误日志

3. 用户体验
   - 响应及时
   - 提供操作反馈
   - 支持快捷操作
   - 界面美观
