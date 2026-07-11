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
            wait_until: 'load',
            timeout: 30000
        }
    },
    {
        keyword: '刷新页面',
        method: "refresh",
        params: {
            wait_until: 'commit',
            timeout: 30000
        }
    },
    {
        keyword: '页面后退',
        method: "go_back",
        params: {
            timeout: 30000,
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
            height: 0,
        }
    },
    {
        keyword: '执行JavaScript脚本',
        method: "execute_script",
        params: {
            script: '',
            args: []
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
            timeout: 20000
        }
    },
    {
        keyword: '点击元素',
        method: "click_ele",
        params: {
            locator: "",
            index: 1,
            force: false,
            timeout: 20000
        }
    },
    {
        keyword: '双击元素',
        method: "double_click_ele",
        params: {
            locator: "",
            index: 1,
            force: false,
            timeout: 20000
        }
    },
    {
        keyword: '清空输入框内容',
        method: "clear_value",
        params: {
            locator: "",
            timeout: 20000
        }
    },
    {
        keyword: '选中复选框',
        method: "set_checked",
        params: {
            locator: "",
            timeout: 20000
        }
    },
    {
        keyword: '鼠标悬停到元素上方',
        method: "hover",
        params: {
            locator: "",
            timeout: 20000
        }
    },
    {
        keyword: '聚焦元素',
        method: "focus_element",
        params: {
            locator: "",
            timeout: 20000
        }
    },
    {
        keyword: '选择下拉框的值',
        method: "select_option",
        params: {
            locator: "",
            value: "",
            timeout: 20000
        }
    },
    {
        keyword: '键盘输入值',
        method: "type_value",
        params: {
            locator: "",
            value: "",
            timeout: 20000
        }
    },
    {
        keyword: '拖拽元素',
        method: "drag_and_drop",
        params: {
            start_selector: "",
            end_selector: "",
            source_position_x: "",
            source_position_y: "",
            target_position_x: "",
            target_position_y: "",
            timeout: 20000
        }
    },
    {
        keyword: '长按元素',
        method: "long_click_element",
        params: {
            locator: "",
            delay: 0.1,
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
            timeout: 20000,
        },
    },
    {
        keyword: '等待图像出现',
        method: 'wait_for_image',
        params: {
            template: '',
            threshold: 0.8,
            timeout: 20000,
        },
    },
    {
        keyword: '断言图像存在',
        method: 'kw_assert_image',
        params: {
            template: '',
            threshold: 0.8,
            timeout: 20000,
        },
    },
    {
        keyword: '断言图像不存在',
        method: 'kw_assert_image_not_exists',
        params: {
            template: '',
            threshold: 0.8,
            timeout: 20000,
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
            x: 0,
            y: 0
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
            timeout: 20000
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
            timeout: 20000
        }
    },
    {
        keyword: 'iframe内元素悬停',
        method: "frame_hover",
        params: {
            frame: "",
            locator: "",
            timeout: 20000
        }
    },
    {
        keyword: 'iframe内元素聚焦',
        method: "frame_focus_element",
        params: {
            frame: "",
            locator: "",
            timeout: 20000
        }
    },
    {
        keyword: 'iframe内下拉框选择',
        method: "frame_select_option",
        params: {
            frame: "",
            locator: "",
            value: "",
            timeout: 20000
        }
    },
    {
        keyword: 'iframe内元素键盘输入',
        method: "frame_type_value",
        params: {
            frame: "",
            value: "",
            locator: "",
            timeout: 20000
        }
    },
    {
        keyword: 'iframe内元素长按',
        method: "frame_long_click_element",
        params: {
            frame: "",
            locator: "",
            delay: 0.1,
        }
    },
    {
        keyword: 'iframe内元素拖拽',
        method: "frame_drag_and_drop",
        params: {
            frame: "",
            start_selector: "",
            end_selector: '',
            source_position_x: "",
            source_position_y: "",
            target_position_x: "",
            target_position_y: "",
            timeout: 20000
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
            timeout: 20000
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
            value: ""
        }
    },
    {
        keyword: '断言元素文本值',
        method: "kw_assert_element_text",
        params: {
            locator: "",
            text: "",
            match_mode: "exact"
        }
    },
    {
        keyword: '断言元素文本包含',
        method: "kw_assert_element_text_contains",
        params: {
            locator: "",
            text: ""
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
        keyword: '断言元素属性值',
        method: "kw_assert_attribute",
        params: {
            locator: "",
            attr_name: "",
            value: ""
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
        keyword: 'input文件上传',
        method: "upload_file",
        params: {
            locator: '',
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
            timeout: 20000
        }
    },
    {
        keyword: '提取元素文本',
        method: "extract_text",
        params: {
            locator: '',
            var_name: '',
            index: 1,
            timeout: 20000
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
            timeout: 20000
        }
    },
    {
        keyword: '提取当前页面url',
        method: "extract_page_url",
        params: {
            var_name: ''
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
