// App 自动化步骤分组（与 backend app_keywords.py、Runner AppEngine KeywordRegistry 对齐）
// Phase 0：关键字骨架；Phase 1 起在 Runner 实现具体逻辑

const appManageSteps = [
    {
        keyword: '启动应用',
        method: 'launch_app',
        params: { app_id: '', stop: false },
    },
    {
        keyword: '启动微信',
        method: 'launch_wechat',
        params: { stop: false },
    },
    {
        keyword: '停止应用',
        method: 'terminate_app',
        params: { app_id: '' },
    },
    {
        keyword: '清除应用数据',
        method: 'clear_app',
        params: { app_id: '' },
    },
    {
        keyword: '安装应用',
        method: 'install_app',
        params: { app_path: '' },
    },
    {
        keyword: '卸载应用',
        method: 'uninstall_app',
        params: { app_id: '' },
    },
]

const elementSteps = [
    {
        keyword: '点击元素',
        method: 'click_element',
        params: {
            locator: { by: 'resource_id', value: '' },
            timeout: 10,
        },
    },
    {
        keyword: '双击元素',
        method: 'double_click_element',
        params: {
            locator: { by: 'resource_id', value: '' },
            timeout: 10,
        },
    },
    {
        keyword: '长按元素',
        method: 'long_press_element',
        params: {
            locator: { by: 'resource_id', value: '' },
            duration: 1.0,
            timeout: 10,
        },
    },
    {
        keyword: '输入文本',
        method: 'input_text',
        params: {
            locator: { by: 'resource_id', value: '' },
            text: '',
            timeout: 10,
        },
    },
    {
        keyword: '清空文本',
        method: 'clear_text',
        params: {
            locator: { by: 'resource_id', value: '' },
            timeout: 10,
        },
    },
    {
        keyword: '获取文本(仅日志)',
        method: 'get_text',
        params: {
            locator: { by: 'resource_id', value: '' },
            timeout: 10,
        },
    },
]

const waitSteps = [
    {
        keyword: '等待元素出现',
        method: 'wait_element',
        params: {
            locator: { by: 'resource_id', value: '' },
            timeout: 10,
        },
    },
    {
        keyword: '等待元素消失',
        method: 'wait_gone',
        params: {
            locator: { by: 'resource_id', value: '' },
            timeout: 10,
        },
    },
    {
        keyword: '强制等待',
        method: 'wait_for_time',
        params: { seconds: 2 },
    },
]

const gestureSteps = [
    {
        keyword: '滑动',
        method: 'swipe',
        params: { direction: 'up' },
    },
    {
        keyword: '滑动至元素',
        method: 'scroll_to',
        params: {
            locator: { by: 'resource_id', value: '' },
        },
    },
]

const assertSteps = [
    {
        keyword: '断言元素存在',
        method: 'assert_exists',
        params: {
            locator: { by: 'resource_id', value: '' },
            timeout: 10,
        },
    },
    {
        keyword: '断言元素不存在',
        method: 'assert_not_exists',
        params: {
            locator: { by: 'resource_id', value: '' },
            timeout: 10,
        },
    },
    {
        keyword: '断言图像存在',
        method: 'assert_image_exists',
        params: {
            locator: { by: 'image', value: '', threshold: 0.8 },
            timeout: 10,
        },
    },
    {
        keyword: '断言图像不存在',
        method: 'assert_image_not_exists',
        params: {
            locator: { by: 'image', value: '', threshold: 0.8 },
            timeout: 10,
        },
    },
    {
        keyword: '断言文本等于',
        method: 'assert_text',
        params: {
            locator: { by: 'resource_id', value: '' },
            text: '',
            timeout: 10,
        },
    },
    {
        keyword: '断言文本包含',
        method: 'assert_text_contains',
        params: {
            locator: { by: 'text', value: '' },
            text: '',
            timeout: 10,
        },
    },
]

const contextSteps = [
    {
        keyword: '切换 WebView',
        method: 'switch_webview',
        params: { page_index: 0, package: '', url: '' },
    },
    {
        keyword: '切换 Chrome',
        method: 'switch_chrome',
        params: { page_index: 0, url: '' },
    },
    {
        keyword: '切回原生',
        method: 'switch_native',
        params: {},
    },
]

const systemSteps = [
    {
        keyword: '按键',
        method: 'press_key',
        params: { key: 'home' },
    },
    {
        keyword: '返回',
        method: 'press_back',
        params: {},
    },
    {
        keyword: '打开链接',
        method: 'open_url',
        params: { url: '' },
    },
    {
        keyword: '截图',
        method: 'screenshot',
        params: { name: 'screenshot' },
    },
    {
        keyword: '提取元素文本',
        method: 'extract_text',
        params: {
            locator: { by: 'resource_id', value: '' },
            var_name: '',
            timeout: 10,
        },
    },
]

const otherSteps = [
    {
        keyword: '数据库断言',
        method: 'kw_db_assert',
        params: {
            datasource_id: null,
            sql: '',
            field: '',
            operator: 'equals',
            expected: '',
        },
    },
]

const conditionSteps = [
    {
        keyword: '条件分支',
        method: 'condition_branch',
        params: {},
        is_container: true,
        branches: [
            {
                id: 'branch_1',
                name: '分支1',
                condition: {
                    type: 'element_exist',
                    locator: { by: 'resource_id', value: '' },
                    expected_value: '',
                },
                steps: [],
            },
            {
                id: 'else_branch',
                name: '默认分支',
                condition: { type: 'else' },
                steps: [],
            },
        ],
    },
]

const appActionGroup = [
    {
        groupId: '1',
        groupIcon: 'Cellphone',
        name: '应用操作',
        items: appManageSteps,
    },
    {
        groupId: '2',
        groupIcon: 'Pointer',
        name: '元素操作',
        items: elementSteps,
    },
    {
        groupId: '3',
        groupIcon: 'Timer',
        name: '等待操作',
        items: waitSteps,
    },
    {
        groupId: '4',
        groupIcon: 'Rank',
        name: '手势操作',
        items: gestureSteps,
    },
    {
        groupId: '5',
        groupIcon: 'CircleCheck',
        name: '断言处理',
        items: assertSteps,
    },
    {
        groupId: '6',
        groupIcon: 'Setting',
        name: '系统操作',
        items: systemSteps,
    },
    {
        groupId: '6b',
        groupIcon: 'Monitor',
        name: 'WebView 上下文',
        items: contextSteps,
    },
    {
        groupId: '7',
        groupIcon: 'MoreFilled',
        name: '其他操作',
        items: otherSteps,
    },
    {
        groupId: '8',
        groupIcon: 'Share',
        name: '条件分支',
        items: conditionSteps,
    },
]

export default appActionGroup

export const allAppSteps = [
    ...appManageSteps,
    ...elementSteps,
    ...waitSteps,
    ...gestureSteps,
    ...assertSteps,
    ...systemSteps,
    ...contextSteps,
    ...otherSteps,
    ...conditionSteps,
]

export {
    appManageSteps,
    elementSteps,
    waitSteps,
    gestureSteps,
    assertSteps,
    systemSteps,
    contextSteps,
    otherSteps,
    conditionSteps,
}

/** Locator by 枚举（控件 + 图像） */
export const APP_LOCATOR_BY_OPTIONS = [
    { label: 'resource-id', value: 'resource_id' },
    { label: '文本', value: 'text' },
    { label: '描述', value: 'description' },
    { label: '类名', value: 'class' },
    { label: 'xpath', value: 'xpath' },
    { label: '坐标', value: 'coordinates' },
    { label: '图像识别', value: 'image' },
]

export const APP_WEBVIEW_LOCATOR_BY_OPTIONS = [
    { label: 'CSS', value: 'css' },
    { label: 'XPath', value: 'xpath' },
    { label: '文本', value: 'text' },
    { label: 'Id', value: 'id' },
]

export const APP_DRIVER_MODE_OPTIONS = [
    { label: '混合（推荐）', value: 'hybrid' },
    { label: '混合 WebView', value: 'hybrid_web' },
    { label: '手机 Chrome H5', value: 'mobile_chrome' },
    { label: '仅控件', value: 'native' },
    { label: '偏图像', value: 'vision' },
]

export const APP_PLATFORM_SCOPE_OPTIONS = [
    { label: 'Android', value: 'android' },
    { label: 'iOS（规划中）', value: 'ios', disabled: true },
    { label: '鸿蒙（规划中）', value: 'harmony', disabled: true },
    { label: '全平台', value: 'all', disabled: true },
]
