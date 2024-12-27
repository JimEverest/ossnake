# OSS高级功能测试文档

## 1. 测试架构设计

### 1.1 测试分离原则
为确保测试的独立性和可维护性，我们为每个OSS服务提供商创建独立的测试类：
tests/
├── test_advanced_ali.py # 阿里云OSS测试
├── test_advanced_aws.py # AWS S3测试
└── test_advanced_minio.py # MinIO测试
每个测试类都继承自 `unittest.TestCase`，并实现自己的 `setUp` 和 `tearDown` 方法。

### 1.2 核心依赖

python
from driver.types import ProgressCallback, OSSConfig, MultipartUpload
from driver.exceptions import TransferError
from driver.transfer_manager import TransferManager

## 2. 测试用例详解

### 2.1 并发上传测试 (test_concurrent_uploads)

#### 2.1.1 测试目标
- 验证OSS客户端能否同时上传多个不同大小的文件
- 确保进度回调准确性
- 验证并发上传的稳定性
- 测试资源清理机制

#### 2.1.2 测试数据准备

```python
test_files = {
'small': 1 1024 1024, # 1MB
'medium': 5 1024 1024, # 5MB
'large': 10 1024 1024 # 10MB
}
```
#### 2.1.3 进度回调实现


```python
class ConcurrentCallback(ProgressCallback):
def init(self):
self.lock = threading.Lock()
self.file_states = {} # 文件状态跟踪
self.logger = logging.getLogger('ConcurrentCallback')
def register_file(self, object_name: str, total_size: int):
"""注册要上传的文件"""
with self.lock:
self.file_states[object_name] = {
'total_size': total_size,
'transferred': 0,
'completed': False,
'progress': 0.0
}
self.logger.info(f"Registered file: {object_name}, size: {total_size}")
```
#### 2.1.4 验证点
1. 文件完整性
   - 所有文件都应完整上传
   - 文件大小与源文件一致
   - 上传后可以正常下载

2. 进度准确性
   - 进度应从0到100%
   - 进度不应回退
   - 进度更新应及时

3. 并发控制
   - 多个文件同时上传不互相影响
   - 线程池正常工作
   - 资源使用合理

4. 错误处理
   - 单个文件失败不影响其他文件
   - 错误信息准确
   - 失败后能正确清理

### 2.2 大文件进度准确性测试 (test_large_file_progress_accuracy)

#### 2.2.1 测试目标
验证大文件上传时进度回调的准确性和可靠性。

#### 2.2.2 测试实现
```python
class AccuracyCallback(ProgressCallback):
def init(self):
self.progress_points = []
self.last_progress = 0
self.lock = threading.Lock()
def on_progress(self, bytes_transferred, total_bytes, start_time, current_speed):
with self.lock:
progress = (bytes_transferred / total_bytes) 100
# 验证进度值的合理性
if not (0 <= progress <= 100):
raise AssertionError(f"Progress out of range: {progress}")
if progress < self.last_progress:
raise AssertionError(f"Progress decreased: {progress} < {self.last_progress}")
self.progress_points.append(progress)
self.last_progress = progress
```





#### 2.2.3 验证点
1. 进度准确性
   - 进度值在0-100%范围内
   - 进度单调递增
   - 最终进度为100%

2. 性能指标
   - 进度更新频率合理
   - 内存使用稳定
   - 网络利用率正常

### 2.3 取消上传测试 (test_cancel_upload)

#### 2.3.1 测试目标
验证在上传过程中取消操作的可靠性。

#### 2.3.2 测试实现






```python
class CancelCallback(ProgressCallback):
def init(self, cancel_at_percent):
self.cancel_at = cancel_at_percent
self.cancelled = False
def on_progress(self, bytes_transferred, total_bytes, start_time, current_speed):
progress = bytes_transferred / total_bytes 100
if progress >= self.cancel_at and not self.cancelled:
self.cancelled = True
raise TransferError(
"Upload cancelled by user",
bytes_transferred,
total_bytes
)

```

#### 2.3.3 验证点
1. 取消操作
   - 能在指定进度点取消
   - 取消操作立即生效
   - 取消后资源释放

2. 资源清理
   - 临时文件被删除
   - 分片上传被中止
   - 服务端资源释放

## 3. 测试运行指南

### 3.1 环境准备
1. 安装依赖


```bash
pip install pytest
pip install oss2 # 阿里云OSS SDK
pip install boto3 # AWS SDK
pip install minio # MinIO SDK

```


2. 配置文件 (config.json)



```json
{
"aliyun": {
"endpoint": "oss-cn-beijing.aliyuncs.com",
"access_key": "your_access_key",
"secret_key": "your_secret_key",
"bucket_name": "test-bucket"
}
}

```
### 3.2 运行测试

#### 单个测试






```bash
# 运行阿里云并发上传测试
python -m pytest tests/test_advanced_ali.py::TestAliyunAdvanced::test_concurrent_uploads -v
# 运行大文件测试
python -m pytest tests/test_advanced_ali.py::TestAliyunAdvanced::test_large_file_progress_accuracy -v

```




#### 所有测试



```bash
# 运行所有阿里云测试
python -m pytest tests/test_advanced_ali.py -v

```


### 3.3 测试结果分析
1. 检查测试日志
2. 验证进度回调数据
3. 确认资源清理情况
4. 分析错误信息（如果有）

## 4. 故障排查指南

### 4.1 常见问题
1. 进度不准确
   - 检查分片大小设置
   - 验证进度计算逻辑
   - 检查网络状况

2. 并发测试失败
   - 检查线程池配置
   - 验证资源限制
   - 检查错误处理

3. 取消操作失效
   - 检查异常处理机制
   - 验证清理流程
   - 检查超时设置

### 4.2 性能优化
1. 调整分片大小
2. 优化并发数
3. 配置合适的超时时间
4. 减少内存使用

## 5. 最佳实践

1. 测试隔离
   - 每个测试方法独立运行
   - 避免测试间相互影响
   - 保持测试环境清洁

2. 错误处理
   - 捕获所有预期异常
   - 验证错误信息准确性
   - 确保资源正确清理

3. 性能考虑
   - 合理设置文件大小
   - 控制并发数量
   - 监控资源使用

4. 日志记录
   - 记录关键操作
   - 保存错误信息
   - 跟踪性能指标









