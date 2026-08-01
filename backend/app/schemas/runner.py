"""Runner 客户端 API Schemas"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Optional

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
    runner_engine_types: list[str] = Field(
        default_factory=lambda: ["web"],
        description="Runner 引擎能力：web|app|perf",
    )
    app_platform: str = Field(default="", description="App 平台 android|ios|harmony")
    app_udid: str = Field(default="", description="adb/hdc 设备序列号")
    app_connection: str = Field(default="", description="usb|wifi")
    toolchain_status: dict[str, Any] = Field(default_factory=dict, description="工具链探活状态")


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
    """Runner 子进程鉴权兜底（与 Backend INTERNAL_API_KEY 一致，仅 connect 下发给已登录用户的 Runner）"""
    internal_api_key: str = ""
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
    runner_notices: Optional[dict[str, Any]] = None
    community_edition: bool = False
    platform_version: str = "1.5.0"
    perf_package_filename: str = "BrickCorePerf.zip"
    perf_package_available: bool = False
    perf_package_size_bytes: int = 0
    perf_package_download_url: str = ""
    perf_package_mac_filename: str = "BrickCorePerf-mac.zip"
    perf_package_mac_available: bool = False
    perf_package_mac_size_bytes: int = 0
    perf_package_mac_download_url: str = ""
    update_manifest: Optional[dict[str, Any]] = None
    update_channels: list[dict[str, Any]] = Field(default_factory=list)
    update_patches_available: bool = False
    update_patches_hint: str = ""


class RunnerReleaseConfigForm(BaseModel):
    external_download_url: str = Field(default="", description="网盘/OSS 直链或分享页 URL")
    external_download_label: str = Field(default="网盘下载", description="下载按钮文案")


class RunnerDisconnectRequest(BaseModel):
    device_id: Optional[str] = None


class RunnerHeartbeatRequest(BaseModel):
    device_id: Optional[str] = None
    client_version: str = ""
    runner_engine_types: Optional[list[str]] = None
    app_platform: str = ""
    app_udid: str = ""
    app_connection: str = ""
    app_capabilities: Optional[dict[str, Any]] = None
    toolchain_status: Optional[dict[str, Any]] = None


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


class RunnerDownloadPresignRequest(BaseModel):
    file_key: str = Field(..., min_length=1, max_length=500)
    bucket: str = Field(default="", max_length=100, description="MinIO bucket，默认 ui-test-files")


class RunnerDownloadPresignResponse(BaseModel):
    download_url: str
    file_key: str
    bucket: str
    expires_in: int = 3600


class RunnerAppTemplateDownloadRequest(BaseModel):
    object_key: str = Field(..., min_length=1, max_length=500)

    @field_validator("object_key")
    @classmethod
    def validate_object_key(cls, value: str) -> str:
        name = value.replace("\\", "/").lstrip("/")
        if not name or ".." in name:
            raise ValueError("非法 object key")
        if not re.match(r"^app-elements/\d+/[a-f0-9]{12}\.(png|jpe?g|webp)$", name, re.I):
            raise ValueError("object key 格式不正确")
        return name


class RunnerFolderManifestRequest(BaseModel):
    folder_key: str = Field(..., min_length=1, max_length=500)
    bucket: str = Field(default="", max_length=100, description="MinIO bucket，默认 ui-test-files")


class RunnerFolderManifestFile(BaseModel):
    relative_path: str
    object_key: str
    download_url: str
    size: int = 0


class RunnerFolderManifestResponse(BaseModel):
    folder_key: str
    folder_name: str = ""
    bucket: str
    files: list[RunnerFolderManifestFile]
    expires_in: int = 3600
