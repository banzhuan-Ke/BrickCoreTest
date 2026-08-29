"""Runner 客户端执行参数单测。"""
from runner_client.app.runner_execution_config import (
    DEFAULT_BROWSER_LAB_GIF_FRAME_SKIP,
    DEFAULT_BROWSER_LAB_GIF_MAX_WIDTH,
    DEFAULT_BROWSER_LAB_STEP_MAX_WIDTH,
    ENV_BROWSER_LAB_GIF_FRAME_SKIP,
    ENV_BROWSER_LAB_GIF_MAX_WIDTH,
    ENV_BROWSER_LAB_STEP_MAX_WIDTH,
    PREF_BROWSER_LAB_GIF_FRAME_SKIP,
    PREF_BROWSER_LAB_GIF_MAX_WIDTH,
    PREF_BROWSER_LAB_STEP_MAX_WIDTH,
    execution_env_from_prefs,
    normalize_execution_prefs,
)


def test_normalize_browser_lab_media_prefs():
    prefs = normalize_execution_prefs(
        {
            PREF_BROWSER_LAB_STEP_MAX_WIDTH: 99999,
            PREF_BROWSER_LAB_GIF_MAX_WIDTH: 100,
            PREF_BROWSER_LAB_GIF_FRAME_SKIP: 9,
        }
    )
    assert prefs[PREF_BROWSER_LAB_STEP_MAX_WIDTH] == 2560
    assert prefs[PREF_BROWSER_LAB_GIF_MAX_WIDTH] == 320
    assert prefs[PREF_BROWSER_LAB_GIF_FRAME_SKIP] == 5


def test_execution_env_includes_browser_lab_keys():
    env = execution_env_from_prefs({})
    assert env[ENV_BROWSER_LAB_STEP_MAX_WIDTH] == str(DEFAULT_BROWSER_LAB_STEP_MAX_WIDTH)
    assert env[ENV_BROWSER_LAB_GIF_MAX_WIDTH] == str(DEFAULT_BROWSER_LAB_GIF_MAX_WIDTH)
    assert env[ENV_BROWSER_LAB_GIF_FRAME_SKIP] == str(DEFAULT_BROWSER_LAB_GIF_FRAME_SKIP)
