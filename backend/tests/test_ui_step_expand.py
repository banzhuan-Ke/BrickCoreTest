"""UI 步骤片段展开单元测试"""
import pytest

from app.core.ui_step_expand import FRAGMENT_REF_METHOD, expand_fragment_refs


@pytest.mark.asyncio
async def test_expand_plain_steps_unchanged():
    steps = [{"id": "s1", "method": "open_url", "params": {"url": "https://a.com"}}]
    result = await expand_fragment_refs(steps, project_id=1)
    assert result == steps


@pytest.mark.asyncio
async def test_expand_missing_fragment_raises():
    ref = {
        "id": "r1",
        "method": FRAGMENT_REF_METHOD,
        "params": {"fragment_id": 999999, "fragment_name": "missing"},
    }
    with pytest.raises(Exception):
        await expand_fragment_refs([ref], project_id=1)
