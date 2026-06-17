"""
LLM 统一客户端封装
支持 OpenAI / DeepSeek / 通义千问 / Claude 等兼容 OpenAI 协议的供应商
支持 OpenAI 标准多模态 messages（Vision 模型读图）
"""
import base64
import logging
from abc import ABC, abstractmethod
from typing import AsyncGenerator, Optional

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


# 各供应商默认 Base URL
DEFAULT_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "claude": "https://api.anthropic.com/v1",
}


class BaseLLMClient(ABC):
    """LLM 客户端抽象基类"""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> dict:
        """
        非流式对话
        :return: {"content": str, "tokens": int}
        """
        pass

    @abstractmethod
    async def chat_stream(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        """流式输出（SSE）"""
        pass


class OpenAIStyleClient(BaseLLMClient):
    """
    兼容 OpenAI 风格的客户端
    适用于：OpenAI / DeepSeek / 通义千问 / 以及任何兼容 OpenAI API 的供应商
    """

    def __init__(
        self,
        api_key: str,
        api_base: Optional[str] = None,
        model: str = "gpt-4o",
        timeout: int = 300,
    ):
        self.api_base = api_base
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=api_base,
            timeout=timeout,
        )
        self.model = model

    async def chat(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        extra_body: dict = None,
        **kwargs,
    ) -> dict:
        import logging
        logger = logging.getLogger(__name__)
        resp = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            extra_body=extra_body,
            **kwargs,
        )
        msg = resp.choices[0].message
        content = msg.content or ""
        tokens = resp.usage.total_tokens if resp.usage else 0
        prompt_tokens = resp.usage.prompt_tokens if resp.usage else 0
        completion_tokens = resp.usage.completion_tokens if resp.usage else 0
        logger.warning(
            f"[llm_client.chat] model={self.model}, content_len={len(content) if content else 0}, "
            f"prompt_tokens={prompt_tokens}, completion_tokens={completion_tokens}, total_tokens={tokens}, "
            f"content_type={type(msg.content)}, has_reasoning={hasattr(msg, 'reasoning_content') and bool(msg.reasoning_content)}"
        )
        return {"content": content, "tokens": tokens}

    async def chat_with_image(
        self,
        system_prompt: str,
        text: str,
        image_bytes: bytes,
        image_mime: str = "image/png",
        temperature: float = 0.3,
        max_tokens: int = 4096,
        extra_body: dict = None,
        **kwargs,
    ) -> dict:
        """Vision 模型：文本 + 单张图片"""
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        data_url = f"data:{image_mime};base64,{b64}"
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": text},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ]
        resp = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            extra_body=extra_body,
            **kwargs,
        )
        msg = resp.choices[0].message
        content = msg.content or ""
        tokens = resp.usage.total_tokens if resp.usage else 0
        logger.info(
            f"[llm_client.chat_with_image] model={self.model}, content_len={len(content)}, tokens={tokens}"
        )
        return {"content": content, "tokens": tokens}

    async def chat_stream(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        extra_body: dict = None,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            extra_body=extra_body,
            **kwargs,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield delta


class LLMClientFactory:
    """LLM 客户端工厂"""

    @staticmethod
    def create(
        provider: str,
        api_key: str,
        api_base: Optional[str] = None,
        model: str = "gpt-4o",
        timeout: int = 300,
    ) -> BaseLLMClient:
        """
        根据供应商创建对应客户端
        """
        # 确定 base_url
        if not api_base:
            api_base = DEFAULT_BASE_URLS.get(provider)

        # 自动补全版本后缀（OpenAI 兼容 API 通常为 /v1；讯飞 MaaS 等新服务使用 /v2）
        if api_base:
            api_base = api_base.rstrip("/")
            if not api_base.endswith(("/v1", "/v2")):
                api_base += "/v1"

        # 目前所有支持的供应商均使用 OpenAI 风格协议
        if provider in ("openai", "deepseek", "qwen", "claude", "custom"):
            return OpenAIStyleClient(
                api_key=api_key,
                api_base=api_base,
                model=model,
                timeout=timeout,
            )

        raise ValueError(f"不支持的 LLM 供应商: {provider}")

    @staticmethod
    def is_likely_vision_model(model: str) -> bool:
        """启发式判断模型是否可能支持 Vision"""
        m = (model or "").lower()
        vision_hints = ("vl", "vision", "gpt-4o", "gpt-4-turbo", "claude-3", "gemini")
        return any(h in m for h in vision_hints)


    @staticmethod
    def create_from_config(config) -> BaseLLMClient:
        """
        从 AiConfig 模型实例创建客户端
        :param config: AiConfig 实例（已解密 api_key）
        """
        return LLMClientFactory.create(
            provider=config.provider,
            api_key=config.api_key,
            api_base=config.api_base,
            model=config.model,
            timeout=config.timeout,
        )
