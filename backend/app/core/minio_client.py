"""
MinIO 客户端工具
用于生成预签名 URL
"""
import logging
import os
import urllib.parse
from datetime import timedelta
from io import BytesIO
from minio import Minio
from app.core.config import (
    AI_REQUIREMENT_BUCKET,
    API_FILE_BUCKET,
    MINIO_CONFIG,
    STORAGE_TYPE,
    UI_TEST_FILE_BUCKET,
)

logger = logging.getLogger(__name__)


class MinioClient:
    """MinIO 客户端封装"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_client()
        return cls._instance
    
    def _init_client(self):
        """初始化 MinIO 客户端"""
        self.endpoint = MINIO_CONFIG['endpoint']
        self.public_endpoint = os.getenv('MINIO_PUBLIC_ENDPOINT', self.endpoint)
        self.secure = MINIO_CONFIG['secure']
        self.access_key = MINIO_CONFIG['access_key']
        self.secret_key = MINIO_CONFIG['secret_key']
        self.bucket_name = MINIO_CONFIG['bucket_name']
        self.api_file_bucket = API_FILE_BUCKET
        
        # 显式指定 region，避免 minio SDK 自动发 HTTP 请求探测 bucket region
        # 否则 MinIO 不可达时会阻塞事件循环（connect timeout 长达 300s）
        minio_region = os.getenv('MINIO_REGION', 'us-east-1')
        
        # 内部客户端（用于上传/下载等容器内操作）
        self.client = Minio(
            endpoint=self.endpoint,
            access_key=self.access_key,
            secret_key=self.secret_key,
            secure=self.secure,
            region=minio_region,
        )
        
        # 外部客户端（用于生成浏览器可访问的预签名 URL）
        if self.public_endpoint != self.endpoint:
            self.public_client = Minio(
                endpoint=self.public_endpoint,
                access_key=self.access_key,
                secret_key=self.secret_key,
                secure=self.secure,
                region=minio_region,
            )
        else:
            self.public_client = self.client
    
    def get_presigned_put_url(
        self,
        filename: str,
        expires: int = 3600,
        content_type: str = "application/octet-stream",
        bucket_name: str | None = None,
    ) -> str | None:
        """生成预签名 PUT URL（Runner 直传对象）"""
        try:
            target_bucket = bucket_name or self.bucket_name
            self._ensure_bucket(target_bucket)
            decoded_filename = urllib.parse.unquote(filename)
            url = self.public_client.presigned_put_object(
                bucket_name=target_bucket,
                object_name=decoded_filename,
                expires=timedelta(seconds=expires),
            )
            return url
        except Exception as e:
            logger.error("[MinIO] 生成预签名 PUT URL 失败: %s", e)
            return None

    def build_public_object_url(self, object_name: str, bucket_name: str | None = None) -> str:
        """构建浏览器/报告使用的对象 URL（私有 bucket，读取时再预签名）"""
        target_bucket = bucket_name or self.bucket_name
        decoded = urllib.parse.unquote(object_name)
        protocol = "https" if self.secure else "http"
        return f"{protocol}://{self.public_endpoint}/{target_bucket}/{decoded}"

    def object_exists(self, object_name: str, bucket_name: str | None = None) -> bool:
        try:
            target_bucket = bucket_name or self.bucket_name
            decoded = urllib.parse.unquote(object_name)
            self.client.stat_object(target_bucket, decoded)
            return True
        except Exception:
            return False

    def get_presigned_url_for_app_element(self, filename: str, expires: int = 7200) -> str | None:
        """为 App 元素库模板生成预签名 URL（兼容历史 api_file_bucket 对象）。"""
        decoded = urllib.parse.unquote(filename)
        buckets = [self.bucket_name]
        if self.api_file_bucket and self.api_file_bucket not in buckets:
            buckets.append(self.api_file_bucket)
        for bucket in buckets:
            if self.object_exists(decoded, bucket):
                return self.get_presigned_url(decoded, expires, bucket)
        return self.get_presigned_url(decoded, expires, self.bucket_name)

    def get_presigned_url(self, filename: str, expires: int = 7200, bucket_name: str = None) -> str:
        """
        生成预签名 URL（使用外部可访问 endpoint，确保签名 host 与浏览器请求一致）
        
        Args:
            filename: 文件名
            expires: 有效期（秒），默认 2 小时
            bucket_name: 桶名，默认主 bucket
            
        Returns:
            预签名 URL
        """
        try:
            target_bucket = bucket_name or self.bucket_name
            self._ensure_bucket(target_bucket)
            # 对文件名进行解码，防止已经 URL encode 过的文件名被二次编码
            decoded_filename = urllib.parse.unquote(filename)
            url = self.public_client.presigned_get_object(
                bucket_name=target_bucket,
                object_name=decoded_filename,
                expires=timedelta(seconds=expires)
            )
            return url
        except Exception as e:
            logger.error("[MinIO] 生成预签名 URL 失败: %s", e)
            return None
    
    def get_batch_presigned_urls(self, filenames: list, expires: int = 7200) -> dict:
        """
        批量生成预签名 URL
        
        Args:
            filenames: 文件名列表
            expires: 有效期（秒）
            
        Returns:
            {filename: url} 字典
        """
        result = {}
        for filename in filenames:
            if filename:
                url = self.get_presigned_url(filename, expires)
                if url:
                    result[filename] = url
        return result
    
    def download_app_element_template(self, object_name: str) -> bytes | None:
        """下载 App 元素库图像模板；兼容历史上传至 api_file_bucket 的对象。"""
        data = self.download_object(object_name, self.bucket_name)
        if data:
            return data
        if self.api_file_bucket and self.api_file_bucket != self.bucket_name:
            return self.download_object(object_name, self.api_file_bucket)
        return None

    def download_object(self, object_name: str, bucket_name: str = None) -> bytes:
        """
        使用内部客户端下载对象（走 docker 内部网络，避免公网回环问题）
        
        Args:
            object_name: 对象名（文件名）
            bucket_name: bucket 名称，不传则使用默认 bucket
            
        Returns:
            文件二进制内容
        """
        try:
            decoded_name = urllib.parse.unquote(object_name)
            target_bucket = bucket_name or self.bucket_name
            response = self.client.get_object(target_bucket, decoded_name)
            data = response.read()
            response.close()
            response.release_conn()
            return data
        except Exception as e:
            print(f"[MinIO] 下载对象失败 ({object_name}): {e}")
            return None

    def upload_bytes(self, object_name: str, data: bytes, content_type: str = "application/octet-stream", bucket_name: str = None):
        try:
            target_bucket = bucket_name or self.api_file_bucket
            self._ensure_bucket(target_bucket)
            self.client.put_object(
                target_bucket,
                object_name,
                BytesIO(data),
                length=len(data),
                content_type=content_type,
            )
            return True
        except Exception as e:
            print(f"[MinIO] 上传对象失败 ({object_name}): {e}")
            return False

    def upload_file(self, object_name: str, file_data, content_type: str = "application/octet-stream", bucket_name: str = None):
        """上传文件流到 MinIO"""
        try:
            target_bucket = bucket_name or self.api_file_bucket
            self._ensure_bucket(target_bucket)
            file_data.seek(0, 2)
            length = file_data.tell()
            file_data.seek(0)
            self.client.put_object(
                target_bucket,
                object_name,
                file_data,
                length=length,
                content_type=content_type,
            )
            return True
        except Exception as e:
            print(f"[MinIO] 上传文件失败 ({object_name}): {e}")
            return False

    def _ensure_bucket(self, bucket_name: str) -> bool:
        """若 bucket 不存在则创建。返回 True 表示本次新建。"""
        if not bucket_name:
            return False
        if self.client.bucket_exists(bucket_name):
            return False
        self.client.make_bucket(bucket_name)
        logger.info("[MinIO] 自动创建 bucket: %s", bucket_name)
        return True

    def ensure_default_buckets(self) -> list[str]:
        """启动时确保平台默认 bucket 存在（Runner 截图 / API 附件 / AI 需求）。"""
        created: list[str] = []
        for name in {self.bucket_name, self.api_file_bucket, AI_REQUIREMENT_BUCKET, UI_TEST_FILE_BUCKET}:
            if name and self._ensure_bucket(name):
                created.append(name)
        if created:
            logger.info("[MinIO] 启动初始化 bucket: %s", ", ".join(created))
        return created


# 全局客户端实例
minio_client = MinioClient()


def is_minio_storage() -> bool:
    """检查是否使用 MinIO 存储"""
    return STORAGE_TYPE.lower() == 'minio'


def init_minio_buckets() -> None:
    """Backend 启动时初始化 MinIO 默认 bucket（同步，lifespan 中放线程池执行）。"""
    if not is_minio_storage():
        return
    minio_client.ensure_default_buckets()
