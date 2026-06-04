"""
AI 测试模块 Pydantic Schema
"""
from typing import Optional, Literal, Any
from pydantic import BaseModel, Field


# ========== AI Config Schemas ==========

class AiConfigBase(BaseModel):
    name: str = Field(default="默认配置", max_length=100)
    provider: Literal["openai", "deepseek", "qwen", "claude", "custom"]
    api_key: str = Field(..., max_length=255)
    api_base: Optional[str] = Field(default=None, max_length=500)
    model: str = Field(default="gpt-4o", max_length=100)
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: int = Field(default=8192, ge=1, le=131072)
    timeout: int = Field(default=60, ge=5, le=1800, description="请求超时(秒)，最长 30 分钟")
    thinking_enabled: bool = Field(default=False, description="是否启用思考模式")
    reasoning_effort: Optional[str] = Field(default="medium", description="推理努力程度(low/medium/high)")
    is_enabled: bool = True


class AiConfigCreate(AiConfigBase):
    pass


class AiConfigUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=100)
    provider: Optional[Literal["openai", "deepseek", "qwen", "claude", "custom"]] = None
    api_key: Optional[str] = Field(default=None, max_length=255)
    api_base: Optional[str] = Field(default=None, max_length=500)
    model: Optional[str] = Field(default=None, max_length=100)
    temperature: Optional[float] = Field(default=None, ge=0, le=2)
    max_tokens: Optional[int] = Field(default=None, ge=1, le=131072)
    timeout: Optional[int] = Field(default=None, ge=5, le=1800)
    thinking_enabled: Optional[bool] = Field(default=None, description="是否启用思考模式")
    reasoning_effort: Optional[str] = Field(default=None, description="推理努力程度(low/medium/high)")
    is_enabled: Optional[bool] = None


class AiConfigOut(BaseModel):
    id: int
    name: str
    provider: str
    api_base: Optional[str]
    model: str
    temperature: float
    max_tokens: int
    timeout: int
    thinking_enabled: bool
    reasoning_effort: Optional[str]
    is_default: bool
    is_enabled: bool
    create_time: str
    update_time: str
    create_by: str

    class Config:
        from_attributes = True


class AiConfigListOut(BaseModel):
    id: int
    name: str
    provider: str
    model: str
    is_default: bool
    is_enabled: bool
    create_time: str

    class Config:
        from_attributes = True


# ========== Prompt Template Schemas ==========

class PromptTemplateOut(BaseModel):
    id: int
    name: str
    code: str
    description: Optional[str]
    scene_type: str
    system_prompt: str
    user_prompt_template: str
    examples: list
    version: int
    is_default: bool
    is_enabled: bool

    class Config:
        from_attributes = True


class PromptTemplateUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=100)
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    user_prompt_template: Optional[str] = None
    examples: Optional[list] = None
    is_enabled: Optional[bool] = None


class PromptTestRequest(BaseModel):
    variables: dict = Field(default_factory=dict)


class PromptTestResponse(BaseModel):
    system_prompt: str
    user_prompt: str
    llm_response: Optional[str] = None


# ========== Common Response ==========

class StandardResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: Optional[Any] = None
