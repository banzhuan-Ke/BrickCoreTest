from app.core.operation_log import compact_log_params, _should_skip_operation_log


def test_compact_log_params_truncates_image_base64():
    data = {"device_id": "123", "image_base64": "A" * 10000, "cache": True}
    out = compact_log_params(data)
    assert out["device_id"] == "123"
    assert out["cache"] is True
    assert out["image_base64"] == "[omitted, length=10000]"


def test_skip_runner_device_screen():
    assert _should_skip_operation_log("/runner/device-screen") is True
    assert _should_skip_operation_log("/runner/device-log") is True


def test_skip_perf_worker_noise():
    assert _should_skip_operation_log("/perf/workers/heartbeat") is True
    assert _should_skip_operation_log("/perf/workers/12/report") is True
    assert _should_skip_operation_log("/perf/workers/unregister") is False
    assert _should_skip_operation_log("/login") is True
