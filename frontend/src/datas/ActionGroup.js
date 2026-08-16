// -----------------操作步骤分组数据---------------------------
// 1、页面操作
const pageSteps = [
    {
        keyword: '打开浏览器',
        method: "open_browser",
        params: {
            browser_type: 'chromium',
        }
    },
    {
        keyword: '访问页面url',
        method: "open_url",
        params: {
            url: '',
            wait_until: 'domcontentloaded',
        }
    },
    {
        keyword: '刷新页面',
        method: "refresh",
        params: {
            wait_until: 'commit',
        }
    },
    {
        keyword: '页面后退',
        method: "go_back",
        params: {
            fallback_url: ''
        }
    },
    {
        keyword: '清空Cookie',
        method: "reset_browser_context",
        params: {}
    },
    {
        keyword: '新建窗口页面',
        method: "open_new_page",
        params: {
            tag: ""
        }
    },
    {
        keyword: '切换页面',
        method: "switch_to_page",
        params: {
            tag: '',
            index: '',
            title: '',
            url: ''
        }
    },
    {
        keyword: '切换到最新页面',
        method: "switch_to_latest_page",
        params: {}
    },
    {
        keyword: '关闭页面',
        method: "close_page",
        params: {
            tag: '',
            index: '',
            title: '',
            url: ''
        }
    },
    {
        keyword: '页面截图',
        method: "save_page_img",
        params: {
            name: ''
        }
    },
    {
        keyword: "关闭浏览器",
        method: "close",
        params: {}
    },
    {
        keyword: '滚动到指定高度位置',
        method: "scroll_to_height",
        params: {
            position: "height",
            height: 0,
        }
    },
    {
        keyword: '滚动到元素',
        method: "scroll_to_element",
        params: {
            locator: '',
            index: 1,
        }
    },
    {
        keyword: '接受弹窗',
        method: "accept_dialog",
        params: {
            prompt_text: ''
        }
    },
    {
        keyword: '取消弹窗',
        method: "dismiss_dialog",
        params: {}
    },
    {
        keyword: '执行JavaScript脚本',
        method: "execute_script",
        params: {
            script: '',
            args: []
        }
    },
    {
        keyword: '设置LocalStorage',
        method: 'set_local_storage',
        params: {
            key: '',
            value: '',
        }
    },
    {
        keyword: '设置SessionStorage',
        method: 'set_session_storage',
        params: {
            key: '',
            value: '',
        }
    },
    {
        keyword: '设置Cookie',
        method: 'add_cookies',
        params: {
            name: '',
            value: '',
            domain: '',
            path: '/',
            url: '',
        }
    },
    {
        keyword: '设置鉴权Token',
        method: 'set_auth_token',
        params: {
            token: '',
            header_name: 'Authorization',
            header_prefix: 'Bearer',
            storage_key: '',
        }
    },
    {
        keyword: '导出登录态',
        method: 'save_storage_state',
        params: {
            path: '',
        }
    }
]
// 2、元素操作
const elementSteps = [
    {
        keyword: '元素输入',
        method: "fill_value",
        params: {
            locator: '',
            value: "",
            index: 1,
        }
    },
    {
        keyword: '点击元素',
        method: "click_ele",
        params: {
            locator: "",
            index: 1,
            force: false,
            ready_selector: '',
            use_env_ready: false,
            expected_selector: '',
            post_wait_state: 'reappear',
            wait_busy_after: false,
            wait_download: false,
            save_path: '',
            var_name: '',
            download_timeout: 60000,
            accept_dialog: false,
            dismiss_dialog: false,
            dialog_timeout: 10000,
            prompt_text: ''
        }
    },
    {
        keyword: '双击元素',
        method: "double_click_ele",
        params: {
            locator: "",
            index: 1,
            force: false,
            ready_selector: '',
            use_env_ready: false,
            expected_selector: '',
            post_wait_state: 'reappear',
            wait_busy_after: false,
        }
    },
    {
        keyword: '清空输入框内容',
        method: "clear_value",
        params: {
            locator: "",
            index: 1,
        }
    },
    {
        keyword: '选中复选框',
        method: "set_checked",
        params: {
            locator: "",
            index: 1,
            ready_selector: '',
            use_env_ready: false,
            expected_selector: '',
            post_wait_state: 'reappear',
            wait_busy_after: false,
        }
    },
    {
        keyword: '鼠标悬停到元素上方',
        method: "hover",
        params: {
            locator: "",
            index: 1,
        }
    },
    {
        keyword: '聚焦元素',
        method: "focus_element",
        params: {
            locator: "",
            index: 1,
        }
    },
    {
        keyword: '选择下拉框的值',
        method: "select_option",
        params: {
            locator: "",
            value: "",
            index: 1,
            ready_selector: '',
            use_env_ready: false,
            expected_selector: '',
            post_wait_state: 'reappear',
            wait_busy_after: false,
        }
    },
    {
        keyword: '键盘输入值',
        method: "type_value",
        params: {
            locator: "",
            value: "",
            index: 1,
        }
    },
    {
        keyword: '拖拽元素',
        method: "drag_and_drop",
        params: {
            start_selector: "",
            end_selector: "",
            source_index: 1,
            target_index: 1,
            source_position_x: "",
            source_position_y: "",
            target_position_x: "",
            target_position_y: "",
            ready_selector: '',
            use_env_ready: false,
            expected_selector: '',
            post_wait_state: 'reappear',
            wait_busy_after: false,
        }
    },
    {
        keyword: '长按元素',
        method: "long_click_element",
        params: {
            locator: "",
            delay: 0.1,
            index: 1,
            ready_selector: '',
            use_env_ready: false,
            expected_selector: '',
            post_wait_state: 'reappear',
            wait_busy_after: false,
        }
    },
    {
        keyword: '按文本点击元素',
        method: "click_by_text",
        params: {
            text: '',
            index: 1,
            exact: false,
            force: false,
            ready_selector: '',
            use_env_ready: false,
            expected_selector: '',
            post_wait_state: 'reappear',
            wait_busy_after: false,
            wait_download: false,
            save_path: '',
            var_name: '',
            download_timeout: 60000,
            accept_dialog: false,
            dismiss_dialog: false,
            dialog_timeout: 10000,
            prompt_text: ''
        }
    },
    {
        keyword: '智能点击',
        method: 'smart_click',
        params: {
            target: '',
            intent: '',
            region: '',
            locator: '',
            target_role: '',
            expected_after: {},
            min_score: 70,
            min_margin: 15,
            allow_ai: false,
            force: false,
        }
    },
    {
        keyword: '智能输入',
        method: 'smart_fill',
        params: {
            target: '',
            intent: '',
            value: '',
            region: '',
            locator: '',
            target_role: '',
            expected_after: {},
            min_score: 70,
            min_margin: 15,
            allow_ai: false,
        }
    },
    {
        keyword: '若存在则点击',
        method: 'click_if_exists',
        params: {
            locator: '',
            index: 1,
            force: false,
            timeout: 5000,
        }
    },
    {
        keyword: '若存在则输入',
        method: 'fill_if_exists',
        params: {
            locator: '',
            value: '',
            index: 1,
            timeout: 5000,
        }
    },
    {
        keyword: '若可见则点击',
        method: 'click_if_visible',
        params: {
            locator: '',
            index: 1,
            force: false,
            timeout: 5000,
        }
    },
    {
        keyword: '若可见则输入',
        method: 'fill_if_visible',
        params: {
            locator: '',
            value: '',
            index: 1,
            timeout: 5000,
        }
    }
]
// 2.5、图像定位（Canvas/纯图标兜底）
const visionSteps = [
    {
        keyword: '图像模板点击',
        method: 'click_by_image',
        params: {
            template: '',
            threshold: 0.8,
        },
    },
    {
        keyword: '图像模板输入',
        method: 'fill_by_image',
        params: {
            template: '',
            value: '',
            threshold: 0.8,
            clear_first: true,
        },
    },
    {
        keyword: '等待图像出现',
        method: 'wait_for_image',
        params: {
            template: '',
            threshold: 0.8,
        },
    },
    {
        keyword: '断言图像存在',
        method: 'kw_assert_image',
        params: {
            template: '',
            threshold: 0.8,
        },
    },
    {
        keyword: '断言图像不存在',
        method: 'kw_assert_image_not_exists',
        params: {
            template: '',
            threshold: 0.8,
        },
    },
]
// 3、鼠标操作步骤
const mouseSteps = [
    {
        keyword: '鼠标点击',
        method: "mouse_click",
        params: {
            x: 0,
            y: 0,
            button: 'left',
            count: 1
        }
    },
    {
        keyword: '鼠标移动',
        method: "move_mouse",
        params: {
            x: 0,
            y: 0,
        }
    },
    {
        keyword: '鼠标按下',
        method: "mouse_down",
        params: {
            button: 'left',
        }
    },
    {
        keyword: '鼠标抬起',
        method: "mouse_up",
        params: {
            button: 'left',
        }
    },
    {
        keyword: '鼠标滚动',
        method: "mouse_wheel",
        params: {
            direction: 'down',
            amount: 600,
            x: 0,
            y: 600,
            cursor_x: '',
            cursor_y: '',
        }
    },
    {
        keyword: '键盘按键',
        method: "press_key",
        params: {
            key: '',
        }
    },
    {
        keyword: '键盘输入文本',
        method: "press_type",
        params: {
            keys: '',
        }
    }
]
// 4、iframe操作
const IframeSteps = [
    {
        keyword: 'iframe内元素输入',
        method: "frame_fill_value",
        params: {
            frame: "",
            locator: '',
            value: "",
            index: 1,
        }
    },
    {
        keyword: 'iframe内元素点击',
        method: "frame_click_element",
        params: {
            frame: "",
            locator: "",
            index: 1,
            button: "left",
            force: false,
            ready_selector: '',
            use_env_ready: false,
            expected_selector: '',
            post_wait_state: 'reappear',
            wait_busy_after: false,
        }
    },
    {
        keyword: 'iframe内元素悬停',
        method: "frame_hover",
        params: {
            frame: "",
            locator: "",
            index: 1,
        }
    },
    {
        keyword: 'iframe内元素聚焦',
        method: "frame_focus_element",
        params: {
            frame: "",
            locator: "",
            index: 1,
        }
    },
    {
        keyword: 'iframe内下拉框选择',
        method: "frame_select_option",
        params: {
            frame: "",
            locator: "",
            value: "",
            index: 1,
            ready_selector: '',
            use_env_ready: false,
            expected_selector: '',
            post_wait_state: 'reappear',
            wait_busy_after: false,
        }
    },
    {
        keyword: 'iframe内元素键盘输入',
        method: "frame_type_value",
        params: {
            frame: "",
            value: "",
            locator: "",
            index: 1,
        }
    },
    {
        keyword: 'iframe内元素长按',
        method: "frame_long_click_element",
        params: {
            frame: "",
            locator: "",
            delay: 0.1,
            index: 1,
            ready_selector: '',
            use_env_ready: false,
            expected_selector: '',
            post_wait_state: 'reappear',
            wait_busy_after: false,
        }
    },
    {
        keyword: 'iframe内元素拖拽',
        method: "frame_drag_and_drop",
        params: {
            frame: "",
            start_selector: "",
            end_selector: '',
            source_index: 1,
            target_index: 1,
            source_position_x: "",
            source_position_y: "",
            target_position_x: "",
            target_position_y: "",
            ready_selector: '',
            use_env_ready: false,
            expected_selector: '',
            post_wait_state: 'reappear',
            wait_busy_after: false,
        }
    }
]
// 5、等待操作
const waitSteps = [
    {
        keyword: '默认等待时间',
        method: "set_default_timeout",
        params: {
            timeout: 20000,
        }
    },
    {
        keyword: '强制等待时间',
        method: "wait_for_time",
        params: {
            timeout: 2000,
        }
    },
    {
        keyword: '等待页面加载完成',
        method: "wait_for_load",
        params: {}
    },
    {
        keyword: '等待网络请求完成',
        method: "wait_for_network",
        params: {}
    },
    {
        keyword: '等待元素可见',
        method: "wait_for_element",
        params: {
            locator: "",
            index: 1,
        }
    },
    {
        keyword: '等待元素可点击',
        method: 'wait_for_clickable',
        params: {
            locator: '',
            index: 1,
        }
    },
    {
        keyword: '等待元素消失',
        method: "wait_for_element_hidden",
        params: {
            locator: "",
            index: 1,
        }
    },
    {
        keyword: '等待元素文本变化',
        method: "wait_for_element_text_change",
        params: {
            locator: "",
            text: '',
            index: 1,
        }
    },
    {
        keyword: '等待元素文本稳定',
        method: "wait_for_element_text_stable",
        params: {
            locator: "",
            stable_ms: 500,
            index: 1,
        }
    },
    {
        keyword: '等待URL包含',
        method: "wait_for_url_contains",
        params: {
            url: '',
            use_regex: false,
        }
    },
    {
        keyword: '等待接口响应',
        method: "wait_for_response",
        params: {
            url: '',
            method: '',
            status: '',
        }
    },
    {
        keyword: '等待下载完成',
        method: "wait_for_download",
        params: {
            save_path: '',
            var_name: ''
        }
    }
]
// 6、断言处理 - 统一使用 kw_assert_* 命名风格（与淘宝源码 except_to_be_* 区分）
const assertSteps = [
    {
        keyword: '断言页面标题',
        method: "kw_assert_page_title",
        params: {
            title: ""
        }
    },
    {
        keyword: '断言页面url地址',
        method: "kw_assert_page_url",
        params: {
            url: ""
        }
    },
    {
        keyword: '断言元素value属性',
        method: "kw_assert_value",
        params: {
            locator: "",
            value: "",
            index: 1,
        }
    },
    {
        keyword: '断言元素文本值',
        method: "kw_assert_element_text",
        params: {
            locator: "",
            text: "",
            match_mode: "exact",
            index: 1,
        }
    },
    {
        keyword: '断言元素文本包含',
        method: "kw_assert_element_text_contains",
        params: {
            locator: "",
            text: "",
            index: 1,
        }
    },
    {
        keyword: '断言文本包含',
        method: "kw_assert_text_contains",
        params: {
            text: ""
        }
    },
    {
        keyword: '断言文本不包含',
        method: "kw_assert_text_not_contains",
        params: {
            text: "",
            locator: "",
            index: 1,
        }
    },
    {
        keyword: '断言元素数量',
        method: "kw_assert_element_count",
        params: {
            locator: "",
            count: 1,
            operator: 'eq'
        }
    },
    {
        keyword: '断言文本长度',
        method: "kw_assert_text_length",
        params: {
            locator: "",
            length: '',
            min_length: '',
            max_length: '',
            operator: 'eq',
            index: 1
        }
    },
    {
        keyword: '断言元素属性值',
        method: "kw_assert_attribute",
        params: {
            locator: "",
            attr_name: "",
            value: "",
            index: 1,
        }
    },
    {
        keyword: '断言元素属性存在',
        method: "kw_assert_attribute_exists",
        params: {
            locator: "",
            attr_name: "",
            index: 1,
        }
    },
    {
        keyword: '断言元素属性不存在',
        method: "kw_assert_attribute_not_exists",
        params: {
            locator: "",
            attr_name: "",
            index: 1
        }
    },
    {
        keyword: '断言元素可见',
        method: "kw_assert_visible",
        params: {
            locator: "",
            index: 1
        }
    },
    {
        keyword: '断言元素隐藏',
        method: "kw_assert_hidden",
        params: {
            locator: "",
            index: 1
        }
    },
    {
        keyword: '断言元素不存在',
        method: "kw_assert_not_exist",
        params: {
            locator: ""
        }
    },
    {
        keyword: '断言元素不可见',
        method: "kw_assert_not_visible",
        params: {
            locator: "",
            index: 1
        }
    },
    {
        keyword: '断言元素可用',
        method: "kw_assert_enabled",
        params: {
            locator: "",
            index: 1
        }
    },
    {
        keyword: '断言元素被禁用',
        method: "kw_assert_disabled",
        params: {
            locator: "",
            index: 1
        }
    },
    {
        keyword: '断言元素被选中',
        method: "kw_assert_checked",
        params: {
            locator: "",
            index: 1
        }
    },
    {
        keyword: '断言元素为空',
        method: "kw_assert_empty",
        params: {
            locator: "",
            index: 1
        }
    },
    {
        keyword: '断言元素可编辑',
        method: "kw_assert_editable",
        params: {
            locator: "",
            index: 1
        }
    },
    {
        keyword: '断言元素获取焦点',
        method: "kw_assert_focused",
        params: {
            locator: "",
            index: 1
        }
    },
    {
        keyword: '断言元素顺序',
        method: "kw_assert_element_order",
        params: {
            first_locator: "",
            second_locator: "",
            order: "before",
            first_index: 1,
            second_index: 1
        }
    },
    {
        keyword: '数据库断言',
        method: "kw_db_assert",
        params: {
            name: '数据库断言',
            datasource_id: null,
            sql: '',
            field: '',
            operator: 'equals',
            expected: ''
        }
    }
]
// 7、其他操作
const otherSteps = [
    {
        keyword: '智能步骤',
        method: 'smart_step',
        params: {
            intent: ''
        }
    },
    {
        keyword: 'input文件上传',
        method: "upload_file",
        params: {
            locator: '',
            index: 1,
            upload_mode: 'single',
            file_path: '',
            file_key: '',
            file_bucket: '',
            file_name: '',
            upload_as_name: '',
            file_items: [],
            folder_key: '',
            folder_bucket: '',
            folder_name: '',
        }
    },
    {
        keyword: '提取元素文本',
        method: "extract_text",
        params: {
            locator: '',
            var_name: '',
            index: 1,
        }
    },
    {
        keyword: '提取元素属性',
        method: "extract_attribute",
        params: {
            locator: '',
            attr_name: '',
            var_name: '',
            index: 1,
        }
    },
    {
        keyword: '提取当前页面url',
        method: "extract_page_url",
        params: {
            var_name: ''
        }
    },
    {
        keyword: '提取接口响应字段',
        method: "extract_response_field",
        params: {
            field: '',
            var_name: '',
            url: '',
            method: '',
            status: '',
        }
    }
]

// 8、条件分支操作
const conditionSteps = [
    {
        keyword: '条件分支',
        method: "condition_branch",
        params: {},
        is_container: true,
        branches: [
            {
                id: 'branch_1',
                name: '分支1',
                condition: {
                    type: 'element_visible',
                    locator: '',
                    operator: 'is_true'
                },
                steps: []
            },
            {
                id: 'else_branch',
                name: '默认分支',
                condition: {type: 'else'},
                steps: []
            }
        ]
    }
]

// 元素操作分类
const actionGroup = [
    {
        groupId: "1",
        groupIcon: 'Document',
        name: '页面操作',
        items: pageSteps,
    },
    {
        groupId: "2",
        groupIcon: 'Edit',
        name: '元素操作',
        items: elementSteps,
    },
    {
        groupId: "2b",
        groupIcon: 'Picture',
        name: '图像定位',
        items: visionSteps,
    },
    {
        groupId: "3",
        groupIcon: 'Mouse',
        name: '鼠标键盘',
        items: mouseSteps,
    },
    {
        groupId: "4",
        groupIcon: 'Clock',
        name: '等待操作',
        items: waitSteps,
    },
    {
        groupId: "5",
        groupIcon: 'Search',
        name: '断言处理',
        items: assertSteps,
    },
    {
        groupId: "6",
        groupIcon: 'MessageBox',
        name: 'iframe操作',
        items: IframeSteps,
    },
    {
        groupId: "7",
        groupIcon: 'MoreFilled',
        name: '其他操作',
        items: otherSteps,
    },
    {
        groupId: "8",
        groupIcon: 'Share',
        name: '条件分支',
        items: conditionSteps,
    }
]

// 导出所有步骤类型
export default actionGroup

// 导出所有步骤的扁平列表（用于拖拽）
export const allSteps = [
    ...pageSteps,
    ...elementSteps,
    ...visionSteps,
    ...mouseSteps,
    ...waitSteps,
    ...assertSteps,
    ...IframeSteps,
    ...otherSteps,
    ...conditionSteps
]

// 导出分组数据
export {
    pageSteps,
    elementSteps,
    visionSteps,
    mouseSteps,
    waitSteps,
    assertSteps,
    IframeSteps,
    otherSteps,
    conditionSteps
}
