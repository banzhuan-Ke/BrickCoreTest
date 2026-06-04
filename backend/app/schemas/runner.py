"""Runner 客户端 API Schemas"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class RunnerConnectRequest(BaseModel):
    id: str = Field(..., description="设备 ID（MAC）")
    ip: str
    name: str
    system: str
    username: str
    version: str = ""
    hostname: str = ""
    client_version: str = "1.0.0"


class RunnerMqConfig(BaseModel):
    host: str
    port: int
    username: str
    password: str
    queue: str


class RunnerRedisConfig(BaseModel):
    host: str
    port: int
    username: str = ""
    password: str
    db: int


class RunnerDatabaseConfig(BaseModel):
    host: str
    port: int
    user: str
    password: str
    database: str


class RunnerConnectResponse(BaseModel):
    device_id: str
    runner_token: str
    runner_token_expires_at: datetime
    base_url: str
    engine_version: str
    client_version_min: str
    client_version_latest: str
    storage_type: str = "minio"
    upload_mode: str = "presigned"
    mq: RunnerMqConfig
    redis: RunnerRedisConfig
    database: Optional[RunnerDatabaseConfig] = None


class RunnerVersionResponse(BaseModel):
    runner_engine_version: str
    runner_client_version_min: str
    runner_client_version_latest: str
    runner_client_download_url: str = ""
    package_filename: str = "BrickCoreRunner.zip"
    package_available: bool = False
    package_size_bytes: int = 0
    package_upload_hint: str = ""
    platform_package_available: bool = False
    external_download_url: str = ""
    external_download_available: bool = False
    external_download_label: str = "网盘下载"
    download_config_source: str = "none"
    storage_mode: str
    middleware_isolation: bool = True


class RunnerReleaseConfigForm(BaseModel):
    external_download_url: str = Field(default="", description="网盘/OSS 直链或分享页 URL")
    external_download_label: str = Field(default="网盘下载", description="下载按钮文案")


class RunnerDisconnectRequest(BaseModel):
    device_id: Optional[str] = None


class RunnerHeartbeatRequest(BaseModel):
    device_id: Optional[str] = None
    client_version: str = ""


class RunnerResultsPayload(BaseModel):
    run_suite: dict = Field(default_factory=dict)
    result: dict = Field(default_factory=dict)


class RunnerEngineReadyRequest(BaseModel):
    id: str
    ip: str = ""
    name: str = ""
    system: str = ""
    username: str = ""
    version: str = ""
    hostname: str = ""
    client_version: str = ""


class RunnerDeviceLogRequest(BaseModel):
    device_id: str = Field(default="", max_length=64)
    message: str = Field(..., min_length=1, max_length=8192)


class RunnerDeviceLogBatchRequest(BaseModel):
    device_id: str = Field(default="", max_length=64)
    messages: list[str] = Field(..., min_length=1, max_length=100)


class RunnerDeviceScreenRequest(BaseModel):
    device_id: str = Field(default="", max_length=64)
    image_base64: str = Field(..., min_length=1)
    format: str = Field(default="jpeg", max_length=16)
    cache: bool = True


class RunnerUploadPresignRequest(BaseModel):
    filename: str = Field(..., min_length=1, max_length=512)
    content_type: str = Field(default="application/octet-stream", max_length=128)

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, value: str) -> str:
        name = value.replace("\\", "/").lstrip("/")
        if not name or ".." in name or name.startswith("/"):
            raise ValueError("非法文件名")
        if not re.match(r"^[A-Za-z0-9_./-]+$", name):
            raise ValueError("文件名仅允许字母、数字、/_-.")
        return name


class RunnerUploadPresignResponse(BaseModel):
    upload_url: str
    object_key: str
    access_url: str
    expires_in: int = 3600
