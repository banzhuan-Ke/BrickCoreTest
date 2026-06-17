"""WebSocket 执行器单元测试"""
import pytest

from app.core.ws_executor import (
    build_ws_response_body,
    ensure_ws_url,
    evaluate_ws_assertion,
    merge_ws_steps,
    run_ws_assertions,
)


def test_ensure_ws_url():
    assert ensure_ws_url("http://localhost:8080/ws") == "ws://localhost:8080/ws"
    assert ensure_ws_url("https://example.com/ws") == "wss://example.com/ws"
    assert ensure_ws_url("ws://localhost/ws") == "ws://localhost/ws"


def test_build_ws_response_body():
    messages = [
        {"direction": "sent", "content": "hi"},
        {"direction": "received", "content": '{"ok": true}'},
    ]
    body = build_ws_response_body(messages)
    assert body["count"] == 1
    assert body["last"] == '{"ok": true}'
    assert body["parsed_last"] == {"ok": True}


def test_ws_assertions():
    body = build_ws_response_body(
        [{"direction": "received", "content": "hello world"}]
    )
    passed, results, _ = run_ws_assertions(
        body,
        {"assertions": [{"type": "ws_contains", "operator": "contains", "expected": "hello"}]},
    )
    assert passed is True
    assert results[0]["passed"] is True


def test_ws_message_count_assertion():
    body = {"count": 2, "combined": "a\nb"}
    passed, actual = evaluate_ws_assertion(
        body,
        {"type": "ws_message_count", "operator": "gte", "expected": 1},
    )
    assert passed is True
    assert actual == 2


def test_merge_ws_steps_case_over_api():
    case = type("C", (), {"ws_steps": [{"action": "send", "message": "x"}]})()
    api = type("A", (), {"ws_config": {"steps": [{"action": "send", "message": "y"}]}})()
    assert merge_ws_steps(case, api)[0]["message"] == "x"

    case2 = type("C", (), {"ws_steps": []})()
    assert merge_ws_steps(case2, api)[0]["message"] == "y"
