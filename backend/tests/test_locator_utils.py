from app.core.locator_utils import (
    coerce_unsafe_has_text_locator,
    extract_locator_text,
    normalize_locator,
    prefer_popup_elements,
    text_unsafe_for_css_has_text,
)


def test_text_unsafe_for_css_has_text():
    assert text_unsafe_for_css_has_text("$24.99")
    assert not text_unsafe_for_css_has_text("2500 Coins")


def test_coerce_has_text_with_dollar():
    raw = 'uni-view:has-text("2500 +220 Coins $24.99")'
    assert coerce_unsafe_has_text_locator(raw) == (
        "uni-view >> get_by_text=2500 +220 Coins $24.99"
    )


def test_coerce_has_text_without_dollar_unchanged():
    raw = 'button:has-text("提交订单")'
    assert coerce_unsafe_has_text_locator(raw) == raw


def test_coerce_chained_has_text_with_dollar():
    raw = 'header >> uni-view:has-text("Coins $24.99")'
    assert normalize_locator(raw) == "header >> uni-view >> get_by_text=Coins $24.99"


def test_coerce_get_by_role_with_dollar_name():
    raw = 'get_by_role=button, Pay $10'
    assert normalize_locator(raw) == raw


def test_normalize_get_by_role_strips_wrapping_quotes():
    raw = "table >> get_by_role='row', 0302"
    assert normalize_locator(raw) == "table >> get_by_role=row, 0302"


def test_normalize_get_by_role_strips_double_quotes():
    raw = 'get_by_role="button", "登录"'
    assert normalize_locator(raw) == "get_by_role=button, 登录"


def test_normalize_get_by_text_strips_wrapping_quotes():
    raw = "get_by_text='提交'"
    assert normalize_locator(raw) == "get_by_text=提交"


def test_normalize_chained_get_by_text_strips_quotes():
    raw = "div.form >> get_by_text='保存'"
    assert normalize_locator(raw) == "div.form >> get_by_text=保存"


def test_normalize_row_shorthand_to_get_by_role():
    raw = "table >> row=0302 徐中柯2 14:16 >> get_by_role=button"
    assert normalize_locator(raw) == "table >> get_by_role=row, 0302 徐中柯2 14:16 >> get_by_role=button"


def test_normalize_cell_shorthand_to_get_by_role():
    raw = "table >> get_by_role=row, 0302 >> cell=4"
    assert normalize_locator(raw) == "table >> get_by_role=row, 0302 >> get_by_role=cell, 4"


def test_normalize_locator_coerces_unsafe_has_text():
    raw = 'uni-view:has-text("2500 +220 Coins $24.99")'
    assert normalize_locator(raw) == "uni-view >> get_by_text=2500 +220 Coins $24.99"


def test_extract_locator_text_from_chained_scope():
    assert extract_locator_text("uni-view.popup >> get_by_text=$24.99") == "$24.99"


def test_prefer_popup_elements():
    raw = [
        {"tag": "button", "text": "主页"},
        {"tag": "uni-view", "text": "$24.99", "in_popup": True},
    ]
    assert len(prefer_popup_elements(raw)) == 1
    assert prefer_popup_elements([{"tag": "button"}]) == [{"tag": "button"}]
