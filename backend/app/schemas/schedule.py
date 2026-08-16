from datetime import datetime
from pydantic import BaseModel, Field
from typing import Any, Optional


class Cronjob(BaseModel):
    """定时任务的任务规则模型类"""
    minute: str = Field(default="30", description="分钟")
    hour: str = Field(default="*", description="小时")
    day: str = Field(default="*", description="天")
    month: str = Field(default="*", description="月")
    day_of_week: str = Field(default="*", description="星期")


class CronDeviceItem(BaseModel):
    """定时任务勾选的执行器（与手动运行 DeviceWeightItem 对齐）"""
    device_id: str = Field(description="执行器 device_id")
    weight: int = Field(default=1, ge=1, le=100, description="套件分配权重")
    concurrency: int = Field(default=1, ge=1, le=20, description="单机套件并发")


class CronRunConfig(BaseModel):
    """持久化到 Cronjob.run_config 的执行器偏好"""
    devices: list[CronDeviceItem] = Field(default_factory=list, description="勾选的 Web 执行器")
    device_id: Optional[str] = Field(default=None, description="串行首选执行器")
    concurrency: int = Field(default=1, ge=1, le=20, description="串行默认并发")
    browser_type: str = Field(default="chromium", description="chromium/firefox/webkit")
    headless: bool = Field(default=True, description="无头模式")


class CronjobSchemas(BaseModel):
    """定时任务响应结构的模型类"""
    id: str = Field(description="任务id")
    name: str = Field(description="任务名称")
    create_time: datetime = Field(description="创建时间")
    project_id: int = Field(description="所属项目")
    env_id: int = Field(description="执行环境")
    task_id: int = Field(description="执行的测试计划")
    state: bool = Field(description="是否启用")
    interval: int = Field(description="执行间隔时间")
    run_type: str = Field(description="任务类型")
    date: datetime = Field(description="指定执行时间")
    crontab: Cronjob = Field(description="周期性任务规则")
    username: str = Field(description="创建人")
    is_del: bool = Field(description="是否删除", default=False)
    run_config: Optional[dict[str, Any]] = Field(default=None, description="执行器配置")

    class Config:
        from_attributes = True  # 支持ORM模型转换


class CronjobForm(BaseModel):
    """定时任务表单"""
    name: str = Field(max_length=50, description="任务名称")
    project: int = Field(description="所属项目")
    env: int = Field(description="执行环境")
    task: int = Field(description="执行的测试计划")
    state: bool = Field(default=False, description="是否启用")
    run_type: str = Field(max_length=10, description="任务类型", default="Interval")
    interval: int = Field(default=60, description="执行间隔时间")
    date: str = Field(default="2030-01-01 00:00:00", description="指定执行时间")
    crontab: Cronjob = Field(default=Cronjob(minute="30", hour="*", day="*", month="*", day_of_week="*"),
                             description="周期性任务规则")
    username: str = Field(max_length=50, description="创建人")
    run_config: Optional[CronRunConfig] = Field(default=None, description="执行器配置")


class CronjobUpdateForm(BaseModel):
    """定时任务更新表单"""
    name: Optional[str] = Field(default=None, max_length=50, description="任务名称")
    project: Optional[int] = Field(default=None, description="所属项目")
    env: Optional[int] = Field(default=None, description="执行环境")
    task: Optional[int] = Field(default=None, description="测试计划")
    state: Optional[bool] = Field(default=None, description="是否启用")
    run_type: Optional[str] = Field(default=None, max_length=10, description="任务类型")
    interval: Optional[int] = Field(default=None, description="执行间隔时间")
    date: Optional[str] = Field(default=None, description="指定执行时间")
    crontab: Optional[Cronjob] = Field(default=None, description="周期性任务规则")
    is_del: Optional[bool] = Field(default=None, description="是否删除（逻辑删除控制）")
    run_config: Optional[CronRunConfig] = Field(default=None, description="执行器配置")
