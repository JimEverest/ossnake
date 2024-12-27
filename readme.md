# OSS 统一存储服务客户端实现文档

## 1. 整体架构

### 1.1 模块关系图
```
driver/
├── base_oss.py       # 基础抽象类,定义统一接口
├── oss_ali.py        # 阿里云OSS实现
├── aws_s3.py         # AWS S3实现  
├── minio_client.py   # MinIO实现
├── transfer_manager.py # 传输管理器
├── exceptions.py     # 异常定义
├── callbacks.py      # 回调接口
├── types.py         # 类型定义
└── models.py        # 数据模型
```

### 1.2 核心模块职责

#### base_oss.py - 统一接口定义
- 定义所有OSS操作的抽象基类
- 确保所有实现遵循相同的接口
- 提供基础的错误处理机制

#### transfer_manager.py - 传输管理
- 处理大文件分片上传
- 管理并发传输
- 提供断点续传能力
- 处理传输进度回调

#### exceptions.py - 异常处理
- 定义统一的异常体系
- 规范化错误信息
- 提供错误追踪能力

#### callbacks.py - 进度回调
- 定义进度通知接口
- 提供标准实现
- 支持自定义扩展

#### models.py - 数据模型
- 定义配置结构
- ���义传输状态模型
- 提供数据验证

## 2. 详细设计

### 2.1 TransferManager 实现

#### 2.1.1 主要功能
1. 分片上传管理
   - 文件分片
   - 并发上传
   - 进度追踪
   - 错误重试

2. 传输控制
   - 暂停/恢复
   - 取消操作
   - 限速控制
   - 资源管理

#### 2.1.2 核心实现
```python
class TransferManager:
    """
    断点续传管理器
    
    功能：
    1. 文件分片管理
    2. 进度保存和恢复
    3. 并发传输控制
    4. 校验和验证
    5. 传输速度控制
    6. 错误重试
    """
    
    CHUNK_SIZE = 5 * 1024 * 1024  # 5MB分片大小
    MAX_WORKERS = 4  # 并发数
    MAX_RETRIES = 3  # 最大重试次数
    
    def __init__(self):
        self.logger = logging.getLogger("TransferManager")
        self.lock = threading.Lock()
        self.start_time = datetime.now()
        self.last_bytes = 0
        self.last_time = self.start_time
```

#### 2.1.3 关键方法说明

1. 上传控制
```python
def upload_file(self, client, local_file, object_name, progress_callback):
    """
    上传文件的主要流程:
    1. 计算文件分片
    2. 初始化分片上传
    3. 并发上传分片
    4. 合并分片完成上传
    5. 错误处理和清理
    """
```

2. 分片管理
```python
def _upload_part(self, client, local_file, upload, part_number, callback):
    """
    单个分片上传:
    1. 读取分片数据
    2. 上传至服务器
    3. 更新进度
    4. 错误重试
    """
```

3. 进度追踪
```python
def _calculate_speed(self, current_bytes):
    """
    计算传输速度:
    1. 计算时间间隔
    2. 计算字节增量
    3. 计算平均速度
    """
```

### 2.2 异常处理系统

#### 2.2.1 异常层次
```
OSSError (基础异常)
├── ConnectionError (连接错误)
├── AuthenticationError (认证错误)
├── ObjectNotFoundError (对象不存在)
├── BucketNotFoundError (存储桶不存在)
├── UploadError (上传错误)
├── DownloadError (下载错误)
└── TransferError (传输错误)
```

#### 2.2.2 异常设计原则
1. 信息完整性
   - 错误消息清晰
   - 包含错误代码
   - 保留原始错误

2. 可追踪性
   - 记录请求ID
   - 保存错误上下文
   - 支持错误堆栈

3. 统一处理
   - 标准化错误转换
   - 统一的错误格式
   - 便于上层处理

### 2.3 回调系统

#### 2.3.1 进度回调接口
```python
class ProgressCallback(ABC):
    """
    进度回调基类
    
    功能：
    1. 通知上传/下载进度
    2. 提供速度信息
    3. 支持自定义处理
    """
    
    @abstractmethod
    def on_progress(
        self,
        bytes_transferred: int,  # 已传输字节数
        total_bytes: int,        # 总字节数
        start_time: datetime,    # 开始时间
        current_speed: float     # 当前速度
    ) -> None:
        pass
```

#### 2.3.2 标准实现
1. 控制台进度条
```python
class ConsoleProgressCallback(ProgressCallback):
    """
    控制台进度显示
    - 显示进度百分比
    - 显示传输速度
    - 显示预估剩余时间
    """
```

2. 文件日志
```python
class FileProgressCallback(ProgressCallback):
    """
    文件进度记录
    - 记录详细的进度信息
    - 支持后续分析
    - 便于调试问题
    """
```

### 2.4 数据模型

#### 2.4.1 配置模型
```python
@dataclass
class OSSConfig:
    """
    OSS配置信息
    
    属性:
    - endpoint: 服务端点
    - access_key: 访问密钥
    - secret_key: 密钥
    - bucket_name: 存储桶名
    - region: 区域
    - secure: 是否使用HTTPS
    - proxy: 代理设置
    """
```

#### 2.4.2 传输进度模型
```python
@dataclass
class TransferProgress:
    """
    传输进度信息
    
    属性:
    - total_size: 总大小
    - transferred: 已传输
    - parts_completed: 分片完成状态
    - start_time: 开始时间
    - last_update: 最后更新时间
    - checksum: 校验和
    - temp_file: 临时文件路径
    """
```

## 3. 实现情况
### 3.1 当前代码中的实际实现情况：
| 功能 | AWS S3 | 阿里云 OSS | MinIO | 实现状态 |
|------|---------|------------|--------|----------|
| 基础上传 | ✓ | ✓ | ✓ | 已完成，通过 _upload_file |
| 流式上传 | ✓ | ✓ | ⚠️ | MinIO需要特殊处理流式上传 |
| 分片上传初始化 | ✓ | ✓ | ⚠️ | MinIO使用时间戳模拟uploadId |
| 分片上传 | ✓ | ✓ | ⚠️ | MinIO需要额外的分片管理 |
| 完成分片上传 | ✓ | ✓ | ⚠️ | MinIO需要手动合并分片 |
| 取消分片上传 | ✓ | ✓ | ⚠️ | MinIO需要手动清理分片 |
| 下载文件 | ✓ | ✓ | ✓ | 基础功能已实现 |
| 删除文件 | ✓ | ✓ | ✓ | 基础功能已实现 |
| 列出对象 | ✓ | ✓ | ✓ | 返回统一的对象信息格式 |
| 预签名URL | ✓ | ✓ | ✓ | 支持过期时间设置 |
| 公共访问URL | ✓ | ✓ | ✓ | 基础功能已实现 |
| Proxy支持 | ✓ | ✓ | ✓ | 通过 http client 配置 |
| 存储桶操作 | ✓ | ✓ | ✓ | 列出/创建/删除已实现 |
| 存储策略 | ✓ | ✓ | ⚠️ | MinIO策略格式需要转换 |


### 3.2 特殊实现差异：
阿里云 OSS (oss_ali.py)

```python
class AliyunOSSClient:
    def _init_client(self):
        # 使用 oss2 SDK
        self.auth = oss2.Auth(self.config.access_key, self.config.secret_key)
        self.bucket = oss2.Bucket(...)
```

AWS S3 (aws_s3.py)

```python
class AWSS3Client:
    def _init_client(self):
        # 使用 boto3 SDK
        self.client = boto3.client('s3', ...)
        self.resource = boto3.resource('s3', ...)
```

MinIO (minio_client.py)

```python
class MinioClient:
    def _init_client(self):
        # 使用 minio SDK
        self.client = Minio(...)
        # 需要特殊处理分片上传
```
### 3.3 待实现功能：
1. 传输管理器增强
[ ] 断点续传持久化
[ ] 传输速度限制
[ ] 更细粒度的进度控制
2. 错误处理完善
[ ] 重试策略配置
[ ] 详细的错误诊断
[ ] 错误统计和报告
性能优化
[ ] 内存使用优化
[ ] 并发参数自适应
[ ] 网络连接池管理
监控和日志
[ ] 详细的操作日志
[ ] 性能指标收集
[ ] 异常监控告警


## 3. 最佳实践

### 3.1 使用建议
1. 大文件上传
   - 使用 TransferManager
   - 设置合适的分片大小
   - 配置适当的并发数

2. 进度回调
   - 实现自定义回调
   - 避免回调中的重操作
   - 注意线程安全

3. 错误处理
   - 捕获具体异常
   - 正确清理资源
   - 实现重试机制

### 3.2 性能优化
1. 传输配置
   - 调整分片大小
   - 设置合适的并发数
   - 配置超时时间

2. 内存管理
   - 控制缓冲区大小
   - 及时释放资源
   - 避免内存泄漏

3. 网络优化
   - 使用断点续传
   - 实现限速控制
   - 处理网络异常

## 4. 常见问题

### 4.1 内存使用
Q: 为什么上传大文件时内存占用高？
A: 检查以下几点：
1. 分片大小设置是否合理
2. 是否及时释放文件句柄
3. 缓冲区大小是否适当

### 4.2 并发控制
Q: 如何控制并发上传的数量？
A: 通过以下方式：
1. 设置 MAX_WORKERS 参数
2. 使用信号量控制并发
3. 实现限速机制

### 4.3 错误处理
Q: 如何处理网络异常？
A: 建议：
1. 实现指数退避重试
2. 保存上传进度
3. 支持断点续传

## 5. 开发指南

### 5.1 添加新的存储服务
1. 继承 BaseOSSClient
2. 实现所有抽象方法
3. 处理特定的错误转换
4. 添加单元测试

### 5.2 扩展功能
1. 实现新的回调接口
2. 添加自定义的异常类型
3. 扩展传输管理器功能
4. 增加新的数据模型

### 5.3 调试技巧
1. 使用日志追踪问题
2. 实现详细的进度回调
3. 保存错误信息
4. 监控资源使用
