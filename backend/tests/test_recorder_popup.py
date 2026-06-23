from app.core.recorder_converter import _insert_popup_wait_actions


def test_insert_popup_wait_on_first_popup_action():
    actions = [
        {
            "action_type": "click",
            "selector": "get_by_text=Chapter 4",
            "timestamp": 1000,
            "meta": {},
        },
        {
            "action_type": "click",
            "selector": "uni-view >> get_by_text=$24.99",
            "element_text": "2500 +220 Coins $24.99",
            "timestamp": 2000,
            "meta": {"popupRoot": "uni-view.popup"},
        },
    ]
    result = _insert_popup_wait_actions(actions)
    assert len(result) == 3
    assert result[1]["action_type"] == "wait_popup"
    assert "$24.99" in result[1]["selector"]
    assert result[2]["action_type"] == "click"


def test_no_popup_wait_when_already_inside_popup():
    actions = [
        {
            "action_type": "click",
            "selector": "uni-view >> get_by_text=$24.99",
            "timestamp": 1000,
            "meta": {"popupRoot": "uni-view.popup"},
        },
        {
            "action_type": "click",
            "selector": "uni-view >> get_by_text=PayPal",
            "timestamp": 2000,
            "meta": {"popupRoot": "uni-view.popup"},
        },
    ]
    result = _insert_popup_wait_actions(actions)
    assert len(result) == 3
    assert result[0]["action_type"] == "wait_popup"
    assert result[1]["action_type"] == "click"
    assert result[2]["action_type"] == "click"
