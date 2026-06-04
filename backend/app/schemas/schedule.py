from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional


class Cronjob(BaseModel):
    """定时任务的任务规则模型类"""
    minute: str = Field(default="30", description="分钟")
    hour: str = Field(default="*", description="小时")
    day: str = Field(default="*", description="天")
    month: str = Field(default="*", description="月")
    day_of_week: str = Field(default="*", description="星期")


class CronjobSchemas(BaseModel):
    """定时任务响应结构的模型类"""
    id: int = Field(description="任务id")
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
    is_del: bool = Field(description="是否删除", default=False)  # 新增：返回删除状态

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


class CronjobUpdateForm(BaseModel):
    """定时任务更新表单"""
    name: Optional[str] = Field(default=None, max_length=50, description="任务名称")
    project: Optional[int] = Field(default=None, description="所属项目")  # 新增：支持修改所属项目
    env: Optional[int] = Field(default=None, description="执行环境")  # 新增：支持修改环境
    task: Optional[int] = Field(default=None, description="测试计划")  # 新增：支持修改计划
    state: Optional[bool] = Field(default=None, description="是否启用")
    run_type: Optional[str] = Field(default=None, max_length=10, description="任务类型")
    interval: Optional[int] = Field(default=None, description="执行间隔时间")
    date: Optional[str] = Field(default=None, description="指定执行时间")
    crontab: Optional[Cronjob] = Field(default=None, description="周期性任务规则")
    is_del: Optional[bool] = Field(default=None, description="是否删除（逻辑删除控制）")  # 新增：删除状态更新