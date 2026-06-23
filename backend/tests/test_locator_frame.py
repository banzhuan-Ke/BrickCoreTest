import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

RUNNER_ROOT = Path(__file__).resolve().parents[2] / "runner"
if str(RUNNER_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNNER_ROOT))

from tools.locator_normalize import resolve_locator_on_frame  # noqa: E402


def test_resolve_locator_on_frame_get_by_text():
    frame = MagicMock()
    text_loc = MagicMock(name="text_locator")
    frame.get_by_text.return_value = text_loc

    result = resolve_locator_on_frame(frame, "get_by_text=提交")

    frame.get_by_text.assert_called_once_with("提交")
    assert result is text_loc


def test_resolve_locator_on_frame_chained_scope():
    frame = MagicMock()
    parent = MagicMock(name="parent_locator")
    child = MagicMock(name="child_locator")
    frame.locator.return_value = parent
    parent.get_by_text.return_value = child

    result = resolve_locator_on_frame(frame, "div.form >> get_by_text=$24.99")

    frame.locator.assert_called_once_with("div.form")
    parent.get_by_text.assert_called_once_with("$24.99")
    assert result is child


def test_resolve_locator_on_frame_three_level_chain():
    frame = MagicMock()
    level1 = MagicMock(name="level1")
    level2 = MagicMock(name="level2")
    level3 = MagicMock(name="level3")
    frame.locator.return_value = level1
    level1.locator.return_value = level2
    level2.get_by_text.return_value = level3

    result = resolve_locator_on_frame(frame, "header >> uni-view >> get_by_text=Coins")

    frame.locator.assert_called_once_with("header")
    level1.locator.assert_called_once_with("uni-view")
    level2.get_by_text.assert_called_once_with("Coins")
    assert result is level3
