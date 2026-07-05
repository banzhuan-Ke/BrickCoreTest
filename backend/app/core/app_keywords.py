"""
App 自动化步骤关键字目录（与 frontend AppActionGroup.js、Runner AppEngine KeywordRegistry 对齐）
"""

APP_VALID_METHODS = {
    "launch_app", "terminate_app", "clear_app", "install_app", "uninstall_app",
    "click_element", "double_click_element", "long_press_element",
    "input_text", "clear_text", "get_text",
    "wait_element", "wait_gone", "wait_for_time",
    "swipe", "scroll_to",
    "assert_exists", "assert_not_exists", "assert_text", "assert_text_contains",
    "extract_text",
    "press_key", "press_back", "open_url", "screenshot",
    "switch_webview", "switch_chrome", "switch_native",
    "condition_branch", "kw_db_assert",
}

APP_REQUIRED_PARAMS = {
    "launch_app": {"app_id"},
    "terminate_app": {"app_id"},
    "clear_app": {"app_id"},
    "install_app": {"app_path"},
    "uninstall_app": {"app_id"},
    "click_element": {"locator"},
    "double_click_element": {"locator"},
    "long_press_element": {"locator"},
    "input_text": {"locator", "text"},
    "clear_text": {"locator"},
    "get_text": {"locator"},
    "wait_element": {"locator"},
    "wait_gone": {"locator"},
    "swipe": set(),
    "scroll_to": {"locator"},
    "assert_exists": {"locator"},
    "assert_not_exists": {"locator"},
    "assert_text": {"locator", "text"},
    "assert_text_contains": {"locator", "text"},
    "extract_text": {"locator", "var_name"},
    "press_key": {"key"},
    "open_url": {"url"},
    "screenshot": {"name"},
    "wait_for_time": {"seconds"},
    "switch_webview": set(),
    "switch_chrome": set(),
    "switch_native": set(),
}

APP_DEFAULT_PARAMS = {
    "click_element": {"timeout": 10},
    "double_click_element": {"timeout": 10},
    "long_press_element": {"timeout": 10, "duration": 1.0},
    "input_text": {"timeout": 10},
    "clear_text": {"timeout": 10},
    "wait_element": {"timeout": 10},
    "wait_gone": {"timeout": 10},
    "wait_for_time": {"seconds": 2},
    "swipe": {"direction": "up"},
    "screenshot": {"name": "screenshot"},
    "launch_app": {"stop": False},
    "switch_webview": {"page_index": 0, "package": "", "url": ""},
    "switch_chrome": {"page_index": 0, "url": ""},
}

APP_LOCATOR_BY_VALUES = {
    "resource_id", "text", "description", "class", "xpath", "coordinates", "image",
    "css", "id",
}

APP_WEBVIEW_LOCATOR_BY_VALUES = {"css", "xpath", "text", "id"}

APP_DRIVER_MODES = {"native", "vision", "hybrid", "hybrid_web", "mobile_chrome"}

APP_PLATFORM_SCOPES = {"android", "ios", "harmony", "all"}

METHOD_TO_KEYWORD = {
    "launch_app": "启动应用",
    "terminate_app": "停止应用",
    "clear_app": "清除应用数据",
    "install_app": "安装应用",
    "uninstall_app": "卸载应用",
    "click_element": "点击元素",
    "double_click_element": "双击元素",
    "long_press_element": "长按元素",
    "input_text": "输入文本",
    "clear_text": "清空文本",
    "get_text": "获取文本",
    "wait_element": "等待元素出现",
    "wait_gone": "等待元素消失",
    "wait_for_time": "强制等待",
    "swipe": "滑动",
    "scroll_to": "滑动至元素",
    "assert_exists": "断言元素存在",
    "assert_not_exists": "断言元素不存在",
    "assert_text": "断言文本等于",
    "assert_text_contains": "断言文本包含",
    "extract_text": "提取元素文本",
    "press_key": "按键",
    "press_back": "返回",
    "open_url": "打开链接",
    "screenshot": "截图",
    "switch_webview": "切换 WebView",
    "switch_chrome": "切换 Chrome",
    "switch_native": "切回原生",
    "condition_branch": "条件分支",
    "kw_db_assert": "数据库断言",
}
