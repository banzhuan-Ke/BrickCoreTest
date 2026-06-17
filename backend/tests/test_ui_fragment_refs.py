"""UI 步骤片段引用扫描单元测试"""
from app.core.ui_fragment_refs import steps_contain_fragment


def test_steps_contain_fragment_top_level():
    steps = [{"method": "fragment_ref", "params": {"fragment_id": 5}}]
    assert steps_contain_fragment(steps, 5) is True
    assert steps_contain_fragment(steps, 6) is False


def test_steps_contain_fragment_in_condition_branch():
    steps = [
        {
            "method": "condition_branch",
            "branches": [
                {"steps": [{"method": "fragment_ref", "params": {"fragment_id": 3}}]},
                {"steps": []},
            ],
        }
    ]
    assert steps_contain_fragment(steps, 3) is True


def test_steps_contain_fragment_empty():
    assert steps_contain_fragment([], 1) is False
    assert steps_contain_fragment(None, 1) is False
