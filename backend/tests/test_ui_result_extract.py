from app.core.ui_result_extract import extract_ui_case_failure_summary


def test_extract_error_from_failed_step_message():
    data = {
        "name": "新建知识库",
        "status": "fail",
        "steps": [
            {"keyword": "open_url", "status": "success", "desc": "打开页面"},
            {"keyword": "click_ele", "status": "fail", "desc": "点击新建", "message": "元素未找到: #add-btn"},
        ],
        "log_data": [["ERROR", "2026-01-01 断言失败: 元素未找到"]],
    }
    summary = extract_ui_case_failure_summary(data)
    assert "元素未找到" in summary["error_hint"]
    assert summary["failed_step_index"] == 2
    assert summary["data_complete"] is True


def test_extract_error_from_log_when_no_message_field():
    data = {
        "name": "用例A",
        "status": "error",
        "steps": [{"keyword": "fill_value", "status": "error", "desc": "填写表单"}],
        "log_data": [["INFO", "开始执行"], ["ERROR", "Timeout 30000ms exceeded"]],
    }
    summary = extract_ui_case_failure_summary(data)
    assert "Timeout" in summary["error_hint"] or "Timeout" in summary["log_error_excerpt"]
