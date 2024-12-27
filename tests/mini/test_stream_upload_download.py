import sys
from pathlib import Path
project_root = str(Path(__file__).parent.parent.parent)
sys.path.insert(0, project_root)

import unittest
import os
import json
import logging
import time
import subprocess
from io import BytesIO
from datetime import datetime
from driver.minio_client import MinioClient
from driver.types import OSSConfig
from tests.utils import SizeFormatter
import tempfile

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TestStreamUploadDownload(unittest.TestCase):
    """测试MinIO流式上传下载"""
    
    def setUp(self):
        """测试初始化"""
        # 加载配置
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
            self.config = OSSConfig(**config['minio'])
        
        self.client = MinioClient(self.config)
        self.video_path = 'tests/example_MP4_1280_10MG.mp4'
        
        # 检查ffmpeg是否可用
        try:
            subprocess.run(['ffmpeg', '-version'], capture_output=True)
        except FileNotFoundError:
            self.skipTest("FFmpeg not found. Please install FFmpeg first.")
            
    def get_video_info(self, file_path):
        """使用ffprobe获取视频信息"""
        cmd = [
            'ffprobe',
            '-v', 'error',   # 只显示错误信息
            '-show_entries', 'format=duration,size',  # 明确指定要获取的信息
            '-show_entries', 'stream=width,height,codec_type',
            '-of', 'json',
            file_path
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                logger.error(f"FFprobe error: {result.stderr}")
                raise RuntimeError(f"FFprobe failed: {result.stderr}")
            
            info = json.loads(result.stdout)
            logger.debug(f"FFprobe output: {json.dumps(info, indent=2)}")
            
            if 'format' not in info:
                logger.error(f"Invalid video file or FFprobe output: {result.stdout}")
                logger.error(f"FFprobe stderr: {result.stderr}")
                raise ValueError("Invalid video format")
            
            return info
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse FFprobe output: {result.stdout}")
            logger.error(f"FFprobe stderr: {result.stderr}")
            raise
    
    def test_video_stream_upload_download(self):
        """测试视频流式上传下载"""
        download_path = 'test_download.mp4'
        temp_file_path = None
        
        try:
            # 1. 获取原始视频信息
            logger.info("Getting original video info...")
            original_info = self.get_video_info(self.video_path)
            original_duration = float(original_info['format']['duration'])
            original_size = int(original_info['format']['size'])
            
            logger.info(f"Original video:")
            logger.info(f"  • Duration: {original_duration:.2f}s")
            logger.info(f"  • Size: {SizeFormatter.format_size(original_size)}")
            
            # 2. 上传视频
            logger.info("\nStarting stream upload...")
            object_name = 'test_stream_video.mp4'
            upload_start = time.time()
            
            # 直接读取文件并上传
            with open(self.video_path, 'rb') as video_file:
                url = self.client.upload_stream(
                    video_file,
                    object_name,
                    content_type='video/mp4'
                )
            
            upload_time = time.time() - upload_start
            upload_speed = original_size / upload_time if upload_time > 0 else 0
            
            logger.info(f"Upload completed:")
            logger.info(f"  • Time: {upload_time:.2f}s")
            logger.info(f"  • Speed: {SizeFormatter.format_size(upload_speed)}/s")
            logger.info(f"  • URL: {url}")
            
            # 验证上传的文件大小
            uploaded_size = self.client.get_object_size(object_name)
            logger.info(f"  • Uploaded Size: {SizeFormatter.format_size(uploaded_size)}")
            
            if uploaded_size != original_size:
                raise ValueError(f"Upload size mismatch: expected {original_size}, got {uploaded_size}")
            
            # 3. 流式下载并验证
            logger.info("\nStarting stream download and verification...")
            verify_start = time.time()
            
            # 定义进度回调
            total_downloaded = 0
            download_start = time.time()
            
            def progress_callback(bytes_downloaded):
                nonlocal total_downloaded
                total_downloaded = bytes_downloaded
                elapsed = time.time() - download_start
                speed = total_downloaded / elapsed if elapsed > 0 else 0
                print(f"\rDownloading: {SizeFormatter.format_size(total_downloaded)} "
                      f"- Speed: {SizeFormatter.format_size(speed)}/s", end='', flush=True)
            
            # 使用临时文件作为中间缓冲
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                temp_file_path = temp_file.name
                
                # 下载到临时文件
                logger.info("Downloading to temporary file...")
                self.client.download_stream(
                    object_name,
                    temp_file,
                    progress_callback=progress_callback
                )
                temp_file.flush()
                
                logger.info("\nProcessing with FFmpeg...")
                
                # 启动ffmpeg进程
                download_cmd = [
                    'ffmpeg',
                    '-f', 'mp4',           # 指定输入格式
                    '-i', temp_file_path,  # 从临时文件读取
                    '-c', 'copy',          # 不重新编码
                    '-movflags', '+faststart+frag_keyframe+empty_moov+default_base_moof',
                    '-vsync', '1',
                    '-async', '1',
                    '-y',
                    download_path
                ]
                
                # 执行ffmpeg命令
                ffmpeg_result = subprocess.run(
                    download_cmd,
                    capture_output=True,
                    text=True
                )
                
                if ffmpeg_result.returncode != 0:
                    logger.error(f"FFmpeg error: {ffmpeg_result.stderr}")
                    raise RuntimeError(f"FFmpeg failed with return code {ffmpeg_result.returncode}")
                
                download_time = time.time() - download_start
                download_speed = total_downloaded / download_time if download_time > 0 else 0
                
                logger.info(f"\nDownload completed:")
                logger.info(f"  • Time: {download_time:.2f}s")
                logger.info(f"  • Speed: {SizeFormatter.format_size(download_speed)}/s")
                
                # 获取下载的视频信息
                downloaded_info = self.get_video_info(download_path)
                downloaded_duration = float(downloaded_info['format']['duration'])
                downloaded_size = int(downloaded_info['format']['size'])
                
                verify_time = time.time() - verify_start
                
                logger.info(f"Downloaded video:")
                logger.info(f"  • Duration: {downloaded_duration:.2f}s")
                logger.info(f"  • Size: {SizeFormatter.format_size(downloaded_size)}")
                logger.info(f"  • Verification Time: {verify_time:.2f}s")
                
                # 4. 验证视频完整性
                duration_diff = abs(original_duration - downloaded_duration)
                logger.info(f"Duration difference: {duration_diff:.3f}s")
                
                # 允许1秒的误差
                MAX_DURATION_DIFF = 1.0  # 1秒
                if duration_diff > MAX_DURATION_DIFF:
                    raise AssertionError(
                        f"Video duration difference too large: {duration_diff:.3f}s > {MAX_DURATION_DIFF}s\n"
                        f"Original: {original_duration:.3f}s\n"
                        f"Downloaded: {downloaded_duration:.3f}s"
                    )
                
                # 验证文件大小（允许一定的误差）
                size_diff = abs(original_size - downloaded_size)
                size_diff_percent = (size_diff / original_size) * 100
                logger.info(f"Size difference: {SizeFormatter.format_size(size_diff)} ({size_diff_percent:.2f}%)")
                
                MAX_SIZE_DIFF_PERCENT = 0.1  # 允许0.1%的大小差异
                if size_diff_percent > MAX_SIZE_DIFF_PERCENT:
                    raise AssertionError(
                        f"Video size difference too large: {size_diff_percent:.2f}% > {MAX_SIZE_DIFF_PERCENT}%\n"
                        f"Original: {SizeFormatter.format_size(original_size)} ({original_size} bytes)\n"
                        f"Downloaded: {SizeFormatter.format_size(downloaded_size)} ({downloaded_size} bytes)\n"
                        f"Difference: {SizeFormatter.format_size(size_diff)}"
                    )
                
                # 5. 清理
                logger.info("\nCleaning up...")
                self.client.delete_file(object_name)
                
                # 6. 输出总统计
                total_time = time.time() - upload_start
                logger.info(f"\nTotal Statistics:")
                logger.info(f"  • Upload Time: {upload_time:.2f}s")
                logger.info(f"  • Download Time: {download_time:.2f}s")
                logger.info(f"  • Total Time: {total_time:.2f}s")
                logger.info(f"  • Average Speed: {SizeFormatter.format_size(original_size/total_time)}/s")
                
        except Exception as e:
            logger.error(f"Error during test: {str(e)}")
            raise
            
        finally:
            # 清理临时文件
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                    logger.debug(f"Removed temporary file: {temp_file_path}")
                except Exception as e:
                    logger.warning(f"Failed to remove temporary file: {e}")
            
            if os.path.exists(download_path):
                try:
                    os.remove(download_path)
                    logger.debug(f"Removed downloaded file: {download_path}")
                except Exception as e:
                    logger.warning(f"Failed to remove downloaded file: {e}")

def main():
    suite = unittest.TestLoader().loadTestsFromTestCase(TestStreamUploadDownload)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    input("\nPress Enter to exit...")

if __name__ == '__main__':
    main()
