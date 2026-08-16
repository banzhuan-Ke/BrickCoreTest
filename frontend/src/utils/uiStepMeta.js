/**
 * UI 步骤参数展示元数据（与 ActionGroup.js / Runner 对齐）
 * 控制步骤编辑弹窗中参数的显示顺序、可见性与标签文案。
 */

const ASSERTION_METHODS = new Set([
  'kw_assert_page_title',
  'kw_assert_page_url',
  'kw_assert_value',
  'kw_assert_element_text',
  'kw_assert_element_text_contains',
  'kw_assert_text_contains',
  'kw_assert_text_not_contains',
  'kw_assert_element_count',
  'kw_assert_text_length',
  'kw_assert_attribute',
  'kw_assert_attribute_exists',
  'kw_assert_attribute_not_exists',
  'kw_assert_visible',
  'kw_assert_hidden',
  'kw_assert_not_exist',
  'kw_assert_not_visible',
  'kw_assert_enabled',
  'kw_assert_disabled',
  'kw_assert_checked',
  'kw_assert_empty',
  'kw_assert_editable',
  'kw_assert_focused',
  'kw_assert_element_order',
  'kw_assert_image',
  'kw_assert_image_not_exists',
])

/** method -> 有序可见参数列表（未列出的 params 字段不展示） */
export const UI_STEP_PARAM_ORDER = {
  open_browser: ['browser_type'],
  open_url: ['url', 'wait_until'],
  scroll_to_height: ['position', 'height'],
  scroll_to_element: ['locator', 'index'],
  accept_dialog: ['prompt_text'],
  dismiss_dialog: [],
  switch_to_latest_page: [],
  execute_script: ['script', 'args'],
  set_local_storage: ['key', 'value'],
  set_session_storage: ['key', 'value'],
  add_cookies: ['name', 'value', 'domain', 'path', 'url'],
  set_auth_token: ['token', 'header_name', 'header_prefix', 'storage_key'],
  save_storage_state: ['path'],
  open_new_page: ['tag'],
  switch_to_page: ['tag', 'index', 'title', 'url'],
  close_page: ['tag', 'index', 'title', 'url'],
  save_page_img: ['name'],
  fill_value: ['locator', 'value', 'index'],
  click_ele: ['locator', 'index', 'force', 'ready_selector', 'use_env_ready', 'expected_selector', 'post_wait_state', 'wait_busy_after', 'wait_download', 'save_path', 'var_name', 'download_timeout', 'accept_dialog', 'dismiss_dialog', 'dialog_timeout', 'prompt_text'],
  click_by_text: ['text', 'index', 'exact', 'force', 'ready_selector', 'use_env_ready', 'expected_selector', 'post_wait_state', 'wait_busy_after', 'wait_download', 'save_path', 'var_name', 'download_timeout', 'accept_dialog', 'dismiss_dialog', 'dialog_timeout', 'prompt_text'],
  smart_click: ['target', 'intent', 'region', 'locator', 'target_role', 'expected_after', 'min_score', 'min_margin', 'allow_ai', 'force'],
  smart_fill: ['target', 'intent', 'value', 'region', 'locator', 'target_role', 'expected_after', 'min_score', 'min_margin', 'allow_ai'],
  click_if_exists: ['locator', 'index', 'force'],
  click_if_visible: ['locator', 'index', 'force'],
  fill_if_exists: ['locator', 'value', 'index'],
  fill_if_visible: ['locator', 'value', 'index'],
  double_click_ele: ['locator', 'index', 'force', 'ready_selector', 'use_env_ready', 'expected_selector', 'post_wait_state', 'wait_busy_after'],
  clear_value: ['locator', 'index'],
  set_checked: ['locator', 'index', 'ready_selector', 'use_env_ready', 'expected_selector', 'post_wait_state', 'wait_busy_after'],
  hover: ['locator', 'index'],
  focus_element: ['locator', 'index'],
  select_option: ['locator', 'value', 'index', 'ready_selector', 'use_env_ready', 'expected_selector', 'post_wait_state', 'wait_busy_after'],
  type_value: ['locator', 'value', 'index'],
  drag_and_drop: ['start_selector', 'end_selector', 'source_index', 'target_index', 'source_position_x', 'source_position_y', 'target_position_x', 'target_position_y', 'timeout', 'ready_selector', 'use_env_ready', 'expected_selector', 'post_wait_state', 'wait_busy_after'],
  long_click_element: ['locator', 'delay', 'index', 'ready_selector', 'use_env_ready', 'expected_selector', 'post_wait_state', 'wait_busy_after'],
  upload_file: ['locator', 'index'],
  click_by_image: ['template', 'threshold'],
  fill_by_image: ['template', 'value', 'clear_first', 'threshold'],
  wait_for_image: ['template', 'threshold'],
  kw_assert_image: ['template', 'threshold'],
  kw_assert_image_not_exists: ['template', 'threshold'],
  mouse_click: ['x', 'y', 'button', 'count'],
  move_mouse: ['x', 'y'],
  mouse_down: ['button'],
  mouse_up: ['button'],
  mouse_wheel: ['direction', 'amount', 'x', 'y', 'cursor_x', 'cursor_y'],
  press_key: ['key'],
  press_type: ['keys'],
  frame_fill_value: ['frame', 'locator', 'value', 'index'],
  frame_click_element: ['frame', 'locator', 'index', 'button', 'force', 'ready_selector', 'use_env_ready', 'expected_selector', 'post_wait_state', 'wait_busy_after'],
  frame_hover: ['frame', 'locator', 'index'],
  frame_focus_element: ['frame', 'locator', 'index'],
  frame_select_option: ['frame', 'locator', 'value', 'index', 'ready_selector', 'use_env_ready', 'expected_selector', 'post_wait_state', 'wait_busy_after'],
  frame_type_value: ['frame', 'locator', 'value', 'index'],
  frame_long_click_element: ['frame', 'locator', 'delay', 'index', 'ready_selector', 'use_env_ready', 'expected_selector', 'post_wait_state', 'wait_busy_after'],
  frame_drag_and_drop: ['frame', 'start_selector', 'end_selector', 'source_index', 'target_index', 'source_position_x', 'source_position_y', 'target_position_x', 'target_position_y', 'timeout', 'ready_selector', 'use_env_ready', 'expected_selector', 'post_wait_state', 'wait_busy_after'],
  set_default_timeout: ['timeout'],
  wait_for_time: ['timeout'],
  wait_for_element: ['locator', 'index'],
  wait_for_clickable: ['locator', 'index'],
  wait_for_element_hidden: ['locator', 'index'],
  wait_for_element_text_change: ['locator', 'text', 'index'],
  wait_for_element_text_stable: ['locator', 'stable_ms', 'index'],
  wait_for_url_contains: ['url', 'use_regex'],
  wait_for_response: ['url', 'method', 'status'],
  wait_for_download: ['save_path', 'var_name'],
  kw_assert_page_title: ['title'],
  kw_assert_page_url: ['url'],
  kw_assert_value: ['locator', 'value', 'index'],
  kw_assert_element_text: ['locator', 'text', 'match_mode', 'index'],
  kw_assert_element_text_contains: ['locator', 'text', 'index'],
  kw_assert_text_contains: ['text'],
  kw_assert_text_not_contains: ['text', 'locator', 'index'],
  kw_assert_element_count: ['locator', 'count', 'operator'],
  kw_assert_text_length: ['locator', 'length', 'min_length', 'max_length', 'operator', 'index'],
  kw_assert_attribute: ['locator', 'attr_name', 'value', 'index'],
  kw_assert_attribute_exists: ['locator', 'attr_name', 'index'],
  kw_assert_attribute_not_exists: ['locator', 'attr_name', 'index'],
  kw_assert_visible: ['locator', 'index'],
  kw_assert_hidden: ['locator', 'index'],
  kw_assert_not_exist: ['locator'],
  kw_assert_not_visible: ['locator', 'index'],
  kw_assert_enabled: ['locator', 'index'],
  kw_assert_disabled: ['locator', 'index'],
  kw_assert_checked: ['locator', 'index'],
  kw_assert_empty: ['locator', 'index'],
  kw_assert_editable: ['locator', 'index'],
  kw_assert_focused: ['locator', 'index'],
  kw_assert_element_order: ['first_locator', 'second_locator', 'order', 'first_index', 'second_index'],
  extract_text: ['locator', 'var_name', 'index'],
  extract_attribute: ['locator', 'attr_name', 'var_name', 'index'],
  extract_input_value: ['locator', 'var_name', 'index'],
  extract_response_field: ['field', 'var_name', 'url', 'method', 'status'],
  smart_step: ['intent'],
}

/** 动作前就绪（UI-1.6）：执行侧已支持，步骤高级配置可编辑 */
const PRE_READY_PARAM_KEYS = ['ready_selector', 'use_env_ready']
/** 点击类：收进「高级配置」的参数（日常二次确认弹窗请拆两步点击，勿用这些） */
const POST_WAIT_PARAM_KEYS = ['expected_selector', 'post_wait_state', 'wait_busy_after']
const PRE_AND_POST_WAIT_KEYS = [...PRE_READY_PARAM_KEYS, ...POST_WAIT_PARAM_KEYS]

export const UI_STEP_ADVANCED_PARAM_KEYS = {
  click_ele: [
    ...PRE_AND_POST_WAIT_KEYS,
    'wait_download', 'save_path', 'var_name', 'download_timeout',
    'accept_dialog', 'dismiss_dialog', 'dialog_timeout', 'prompt_text',
  ],
  click_by_text: [
    ...PRE_AND_POST_WAIT_KEYS,
    'wait_download', 'save_path', 'var_name', 'download_timeout',
    'accept_dialog', 'dismiss_dialog', 'dialog_timeout', 'prompt_text',
  ],
  double_click_ele: [...PRE_AND_POST_WAIT_KEYS],
  set_checked: [...PRE_AND_POST_WAIT_KEYS],
  select_option: [...PRE_AND_POST_WAIT_KEYS],
  long_click_element: [...PRE_AND_POST_WAIT_KEYS],
  drag_and_drop: [...PRE_AND_POST_WAIT_KEYS],
  frame_click_element: [...PRE_AND_POST_WAIT_KEYS],
  frame_select_option: [...PRE_AND_POST_WAIT_KEYS],
  frame_long_click_element: [...PRE_AND_POST_WAIT_KEYS],
  frame_drag_and_drop: [...PRE_AND_POST_WAIT_KEYS],
}

export function getStepAdvancedParamKeys(method) {
  return UI_STEP_ADVANCED_PARAM_KEYS[method] || []
}

export function hasStepAdvancedParams(method) {
  return getStepAdvancedParamKeys(method).length > 0
}

/** method + paramKey -> 展示标签（覆盖通用标签） */
export const UI_STEP_PARAM_LABELS = {
  fill_by_image: {
    value: '输入内容',
    clear_first: '输入前清空',
  },
  drag_and_drop: {
    source_position_x: '起始落点X(像素)',
    source_position_y: '起始落点Y(像素)',
    target_position_x: '目标落点X(像素)',
    target_position_y: '目标落点Y(像素)',
    source_index: '起始元素顺序索引',
    target_index: '目标元素顺序索引',
    ready_selector: '动作前就绪选择器',
    use_env_ready: '使用环境就绪选择器',
    expected_selector: '动作后等待选择器',
    post_wait_state: '动作后等待状态',
    wait_busy_after: '动作后再等忙碌遮罩',
  },
  frame_drag_and_drop: {
    source_position_x: '起始落点X(像素)',
    source_position_y: '起始落点Y(像素)',
    target_position_x: '目标落点X(像素)',
    target_position_y: '目标落点Y(像素)',
    source_index: '起始元素顺序索引',
    target_index: '目标元素顺序索引',
    ready_selector: '动作前就绪选择器',
    use_env_ready: '使用环境就绪选择器',
    expected_selector: '动作后等待选择器',
    post_wait_state: '动作后等待状态',
    wait_busy_after: '动作后再等忙碌遮罩',
  },
  kw_assert_page_title: { title: '预期标题' },
  kw_assert_page_url: { url: '预期URL' },
  scroll_to_height: {
    position: '滚动方式',
    height: '高度 / 距离(像素)',
  },
  mouse_wheel: {
    direction: '滚动方向',
    amount: '滚动量(像素)',
    x: '水平滚动量 ΔX',
    y: '垂直滚动量 ΔY',
    cursor_x: '光标 X（可选）',
    cursor_y: '光标 Y（可选）',
  },
  set_local_storage: {
    key: '键名',
    value: '值（支持 ${{变量}}）',
  },
  set_session_storage: {
    key: '键名',
    value: '值（支持 ${{变量}}）',
  },
  add_cookies: {
    name: 'Cookie 名',
    value: 'Cookie 值',
    domain: 'Domain（可选）',
    path: 'Path',
    url: 'URL（可选，与 domain 二选一）',
  },
  set_auth_token: {
    token: 'Token / 凭证',
    header_name: '请求头名',
    header_prefix: '前缀（如 Bearer）',
    storage_key: '同步写入 LocalStorage 键（可选，写入纯 Token 字符串）',
  },
  save_storage_state: {
    path: '导出路径（执行机本机）',
  },
  kw_assert_value: { value: '预期value' },
  kw_assert_element_text: { text: '预期文本', match_mode: '匹配方式' },
  kw_assert_element_text_contains: { text: '预期包含文本' },
  kw_assert_text_contains: { text: '预期包含文本' },
  kw_assert_text_not_contains: { text: '不应包含的文本', locator: '元素定位（可选，留空则检查整页）' },
  kw_assert_element_count: { count: '期望数量', operator: '比较方式(eq/gte/lte)' },
  kw_assert_text_length: {
    length: '精确长度',
    min_length: '最小长度',
    max_length: '最大长度',
    operator: '比较方式(eq/gte/lte)',
    locator: '元素定位（可选）',
  },
  kw_assert_attribute: { value: '预期属性值', attr_name: '属性名称' },
  kw_assert_attribute_exists: { attr_name: '属性名称' },
  kw_assert_attribute_not_exists: { attr_name: '属性名称' },
  kw_assert_visible: { index: '顺序索引' },
  kw_assert_hidden: { index: '顺序索引' },
  kw_assert_not_visible: { index: '顺序索引' },
  kw_assert_enabled: { index: '顺序索引' },
  kw_assert_disabled: { index: '顺序索引' },
  kw_assert_checked: { index: '顺序索引' },
  kw_assert_empty: { index: '顺序索引' },
  kw_assert_editable: { index: '顺序索引' },
  kw_assert_focused: { index: '顺序索引' },
  kw_assert_element_order: {
    first_locator: '靠前元素定位',
    second_locator: '靠后参照元素定位',
    order: '期望顺序',
    first_index: '靠前元素索引',
    second_index: '参照元素索引',
  },
  click_ele: {
    wait_download: '点击后等待文件下载',
    save_path: '下载保存路径',
    var_name: '下载路径变量名',
    download_timeout: '下载超时(毫秒)',
    accept_dialog: '自动点原生弹窗「确定」',
    dismiss_dialog: '自动点原生弹窗「取消」',
    dialog_timeout: '等待原生弹窗超时',
    prompt_text: 'prompt 弹窗输入内容',
    ready_selector: '动作前就绪选择器',
    use_env_ready: '使用环境就绪选择器',
    expected_selector: '动作后等待选择器',
    post_wait_state: '动作后等待状态',
    wait_busy_after: '动作后再等忙碌遮罩',
  },
  click_by_text: {
    wait_download: '点击后等待文件下载',
    save_path: '下载保存路径',
    var_name: '下载路径变量名',
    download_timeout: '下载超时(毫秒)',
    accept_dialog: '自动点原生弹窗「确定」',
    dismiss_dialog: '自动点原生弹窗「取消」',
    dialog_timeout: '等待原生弹窗超时',
    prompt_text: 'prompt 弹窗输入内容',
    ready_selector: '动作前就绪选择器',
    use_env_ready: '使用环境就绪选择器',
    expected_selector: '动作后等待选择器',
    post_wait_state: '动作后等待状态',
    wait_busy_after: '动作后再等忙碌遮罩',
  },
  smart_click: {
    target: '要点谁',
    intent: '本步要做什么',
    region: '在哪个区域',
    locator: '候选定位（可选）',
    target_role: '控件类型（可选）',
    expected_after: '点完后应看到',
    min_score: '最低置信分',
    min_margin: '与第二名最小分差',
    allow_ai: '允许 AI 补候选',
    force: '强制点击（被遮挡时）',
  },
  smart_fill: {
    target: '要填哪一格',
    intent: '本步要做什么',
    value: '输入内容',
    region: '在哪个区域',
    locator: '候选定位（可选）',
    target_role: '控件类型（可选）',
    expected_after: '填完后应看到（可选）',
    min_score: '最低置信分',
    min_margin: '与第二名最小分差',
    allow_ai: '允许 AI 补候选',
  },
  double_click_ele: {
    ready_selector: '动作前就绪选择器',
    use_env_ready: '使用环境就绪选择器',
    expected_selector: '动作后等待选择器',
    post_wait_state: '动作后等待状态',
    wait_busy_after: '动作后再等忙碌遮罩',
  },
  set_checked: {
    ready_selector: '动作前就绪选择器',
    use_env_ready: '使用环境就绪选择器',
    expected_selector: '动作后等待选择器',
    post_wait_state: '动作后等待状态',
    wait_busy_after: '动作后再等忙碌遮罩',
  },
  select_option: {
    ready_selector: '动作前就绪选择器',
    use_env_ready: '使用环境就绪选择器',
    expected_selector: '动作后等待选择器',
    post_wait_state: '动作后等待状态',
    wait_busy_after: '动作后再等忙碌遮罩',
  },
  long_click_element: {
    ready_selector: '动作前就绪选择器',
    use_env_ready: '使用环境就绪选择器',
    expected_selector: '动作后等待选择器',
    post_wait_state: '动作后等待状态',
    wait_busy_after: '动作后再等忙碌遮罩',
  },
  frame_click_element: {
    ready_selector: '动作前就绪选择器',
    use_env_ready: '使用环境就绪选择器',
    expected_selector: '动作后等待选择器',
    post_wait_state: '动作后等待状态',
    wait_busy_after: '动作后再等忙碌遮罩',
  },
  frame_select_option: {
    ready_selector: '动作前就绪选择器',
    use_env_ready: '使用环境就绪选择器',
    expected_selector: '动作后等待选择器',
    post_wait_state: '动作后等待状态',
    wait_busy_after: '动作后再等忙碌遮罩',
  },
  frame_long_click_element: {
    ready_selector: '动作前就绪选择器',
    use_env_ready: '使用环境就绪选择器',
    expected_selector: '动作后等待选择器',
    post_wait_state: '动作后等待状态',
    wait_busy_after: '动作后再等忙碌遮罩',
  },
  smart_step: {
    intent: '步骤意图',
  },
}

const DRAG_DROP_TOOLTIPS = {
  source_position_x:
    '相对「起始元素」左上角的横向像素，一般 10~30。与 source_position_y 成对填写；都留空则从元素中心抓起。',
  source_position_y:
    '相对「起始元素」左上角的纵向像素，一般取元素垂直中线附近（如 15）。与 source_position_x 成对填写；都留空则从元素中心抓起。',
  target_position_x:
    '相对「结束元素」左上角的横向像素，一般 10~30（避开左侧折叠图标）。须与 target_position_y 同时填写；都留空则落在元素中心（树组件易变成拖入子级）。',
  target_position_y:
    '相对「结束元素」左上角的纵向像素，决定同级排序位置：\n'
    + '• Y 较小（如 3~8）：松手在节点上沿 → 插到该节点前面\n'
    + '• Y 较大（接近节点高度 - 5）：松手在下沿 → 插到该节点后面\n'
    + '• 落在中间：易被识别为拖入子级\n\n'
    + '示例：把「目录2」插到「目录1」前 → 结束元素选目录1，target X=20，target Y=5',
}

const ELEMENT_ORDER_TOOLTIPS = {
  first_locator:
    '在 DOM 文档顺序中应更靠前的元素。例：断言「目录2」在「目录1」前面时，此处填目录2 的定位。',
  second_locator:
    '作为参照的元素，第一个元素应相对它更靠前或更靠后（由「期望顺序」决定）。上例中填目录1 的定位。',
  order:
    '• 前面：第一个元素在第二个元素之前（同级列表/树节点上移）\n'
    + '• 后面：第一个元素在第二个元素之后\n\n'
    + '也可通过交换两个定位表达式达到同样效果。',
  first_index: '当靠前元素定位匹配多个节点时，取第几个（从 1 开始）。',
  second_index: '当参照元素定位匹配多个节点时，取第几个（从 1 开始）。',
}

/** iframe 操作共用：frame 参数悬浮教程 */
export const FRAME_LOCATOR_TOOLTIP =
  '定位页面上的 iframe 框本身（不是框内按钮/输入框）。\n\n'
  + '推荐写法：\n'
  + '• 有唯一 id：#myFrame\n'
  + '• 有唯一 class：.myFrame\n'
  + '• 按 src 片段（多个 iframe 时常用）：iframe[src*="somePath"]\n'
  + '• 按完整 src：iframe[src="/module/page/index"]\n'
  + '• 只操作当前显示的 tab iframe：\n'
  + '  #tabs_iframe .tabsIframeBlock:not([style*="display: none"]) iframe\n\n'
  + '常见错误：\n'
  + '• 不要写 src=/xxx 或 src="..."（会报 Unknown engine "src"）\n'
  + '• 多个 iframe 共用同一 id 时，不要用 #frameCon\n\n'
  + '「顺序索引」只作用于 iframe 内的元素，不能用来选第几个 iframe。'

/** method + paramKey -> 参数悬浮说明 */
export const UI_STEP_PARAM_TOOLTIPS = {
  drag_and_drop: DRAG_DROP_TOOLTIPS,
  frame_drag_and_drop: {
    ...DRAG_DROP_TOOLTIPS,
    frame: FRAME_LOCATOR_TOOLTIP,
  },
  kw_assert_element_order: ELEMENT_ORDER_TOOLTIPS,
  frame_fill_value: { frame: FRAME_LOCATOR_TOOLTIP },
  frame_click_element: { frame: FRAME_LOCATOR_TOOLTIP },
  frame_hover: { frame: FRAME_LOCATOR_TOOLTIP },
  frame_focus_element: { frame: FRAME_LOCATOR_TOOLTIP },
  frame_select_option: { frame: FRAME_LOCATOR_TOOLTIP },
  frame_type_value: { frame: FRAME_LOCATOR_TOOLTIP },
  frame_long_click_element: { frame: FRAME_LOCATOR_TOOLTIP },
  click_by_text: {
    text: '页面上可见的文本内容',
    exact: '是否精确匹配（默认模糊匹配）',
    index: '第几个匹配项（从 1 开始）',
    wait_download:
      '用于点「导出/下载」按钮后等待浏览器下载完成，不是上传文件。\n'
      + '页面二次确认请另加一步点击确定，不要用下面的原生弹窗开关。',
    save_path: '指定保存路径；留空则使用浏览器临时目录',
    var_name: '将下载文件路径写入用例变量，供后续步骤引用',
    download_timeout: '等待下载完成的最长时间，默认 60000ms',
    accept_dialog:
      '仅处理浏览器系统弹窗（window.alert / confirm / prompt）的「确定」。\n'
      + '页面自己画的二次确认对话框请拆成两步：先点触发按钮，再点「确定」。',
    dismiss_dialog:
      '仅处理浏览器系统 confirm/prompt 的「取消」。\n'
      + '与「自动点原生弹窗确定」互斥；页面组件弹窗请另加点击步骤。',
    dialog_timeout: '等待原生系统弹窗出现的最长时间，默认 10000ms',
    prompt_text: '若是 prompt 输入框，这里填写要自动输入的文本',
    ready_selector:
      '本步动作前额外等待的业务就绪点（如主表单已渲染）。\n'
      + '与环境「就绪选择器」独立；一般点击前默认只等忙碌遮罩，需要时再填。',
    use_env_ready:
      '开启后，本步动作前也会等待环境配置的就绪选择器。\n'
      + '默认关闭，避免每次点击都被环境 ready 挡住。',
    expected_selector:
      '动作后的业务变化点，不要填页面上一直存在的表格壳/菜单/标题。\n'
      + '推荐：成功提示、加载完成后才出现的空态文案、结果计数变化对应节点。\n'
      + '查询/保存后列表刷新请用状态「先消失再出现」。',
    post_wait_state:
      'reappear（推荐）= 已可见则先等消失再等出现，避免抢跑；\n'
      + 'visible=仅等出现（常驻元素会立刻成功）；hidden=仅等消失',
    wait_busy_after: '额外再短探测环境忙碌遮罩；一般填「动作后等待选择器」即可',
  },
  smart_click: {
    target: '要点击的文案或语义，如「新增」「提交」',
    intent: '用一句话说明本步目的，便于报告与消歧，必填',
    region: '缩小查找范围，如「顶部操作栏」「确认删除弹窗」；危险动作必填',
    locator: '可选；录制或 AI 自愈得到的定位，作为消歧候选之一',
    target_role: '可选 role，如 button；与目标文案组成更稳的候选',
    expected_after:
      '点完后页面应出现/消失的内容。删除、提交等危险动作必填。'
      + '用下方表单选择类型即可，无需手写 JSON。',
    min_score: '低于此分拒绝点击，默认 70（满分约 100）',
    min_margin: '与第二名分差不足则视为歧义并失败，默认 15',
    allow_ai: '预留开关，当前版本暂不生效',
    force: '元素被遮挡时尝试强制点击',
  },
  smart_fill: {
    target: '要填充的字段语义，如「用户名」「手机号」',
    intent: '用一句话说明本步目的，必填',
    value: '要写入输入框的内容',
    region: '表单/弹窗区域提示，同页多字段同名时必填',
    locator: '可选初始候选定位',
    target_role: '通常为 textbox',
    expected_after:
      '可不填；未配置时执行侧默认校验输入值等于本次内容。'
      + '需要更严校验时用下方表单选择类型。',
    min_score: '低于此分拒绝输入，默认 70',
    min_margin: '与第二名分差不足则视为歧义并失败，默认 15',
    allow_ai: '预留开关，当前版本暂不生效',
  },
  click_ele: {
    force: '元素被遮挡时尝试强制点击',
    wait_download:
      '用于点「导出/下载」按钮后等待浏览器下载完成，不是上传文件。\n'
      + '页面二次确认请另加一步点击确定，不要用下面的原生弹窗开关。',
    save_path: '指定保存路径；留空则使用浏览器临时目录',
    var_name: '将下载文件路径写入用例变量，供后续步骤引用',
    download_timeout: '等待下载完成的最长时间，默认 60000ms',
    accept_dialog:
      '仅处理浏览器系统弹窗（window.alert / confirm / prompt）的「确定」。\n'
      + '页面自己画的二次确认对话框请拆成两步：先点触发按钮，再点「确定」。',
    dismiss_dialog:
      '仅处理浏览器系统 confirm/prompt 的「取消」。\n'
      + '与「自动点原生弹窗确定」互斥；页面组件弹窗请另加点击步骤。',
    dialog_timeout: '等待原生系统弹窗出现的最长时间，默认 10000ms',
    prompt_text: '若是 prompt 输入框，这里填写要自动输入的文本',
    ready_selector:
      '本步动作前额外等待的业务就绪点（如主表单已渲染）。\n'
      + '与环境「就绪选择器」独立；一般点击前默认只等忙碌遮罩，需要时再填。',
    use_env_ready:
      '开启后，本步动作前也会等待环境配置的就绪选择器。\n'
      + '默认关闭，避免每次点击都被环境 ready 挡住。',
    expected_selector:
      '动作后的业务变化点，不要填页面上一直存在的表格壳/菜单/标题。\n'
      + '推荐：成功提示、加载完成后才出现的空态文案、结果计数变化对应节点。\n'
      + '查询/保存后列表刷新请用状态「先消失再出现」。',
    post_wait_state:
      'reappear（推荐）= 已可见则先等消失再等出现，避免抢跑；\n'
      + 'visible=仅等出现（常驻元素会立刻成功）；hidden=仅等消失',
    wait_busy_after: '额外再短探测环境忙碌遮罩；一般填「动作后等待选择器」即可',
  },
  hover: {
    locator: '悬停目标定位器；同文案多处出现时配合下标',
    index: '同定位器匹配多个时取第几个（从 1 开始）。录制/拾取可能自动写入；定位器已唯一时请保持 1。',
  },
  frame_hover: {
    frame: 'iframe 定位',
    locator: 'iframe 内悬停目标',
    index: '同定位器匹配多个时取第几个（从 1 开始）',
  },
  focus_element: {
    index: '同定位器匹配多个时取第几个（从 1 开始）',
  },
  wait_for_url_contains: {
    url: '当前页面 URL 应包含的片段；默认按字面子串匹配',
    use_regex: '开启后将 url 当作正则（默认关闭，避免把普通路径误当正则）',
  },
  scroll_to_height: {
    position:
      '优先滚动页面里真正带滚动条的区域（含 SPA 主内容区）；仅滚不动时再用鼠标滚轮兜底。\n'
      + '「顶部/中间/底部」：滚到该区域绝对位置；「向上/向下」：相对当前再滚一段；「指定高度」：滚到距顶部的像素。',
    height:
      '「指定高度」：距滚动区域顶部的绝对像素（0=顶部）。\n'
      + '「向上/向下」：每次相对滚动的距离，建议 600～1500。\n'
      + '若仍无效果：目标可能在弹层/表格内部，请改用「滚动到元素」。',
  },
  mouse_wheel: {
    direction:
      '在鼠标光标下方派发滚轮事件（不是把页面 scrollTop 设到某值）。\n'
      + '优先用「向下/向上/向左/向右」；需要同时水平+垂直时选「自定义」。',
    amount: '相对滚动量，建议 600～1500。正数方向由「滚动方向」决定。',
    x:
      '水平滚轮增量：正数向右滚，负数向左。\n'
      + '不是屏幕坐标；日常页面上下滚动请用「垂直滚动量」或方向预设。',
    y:
      '垂直滚轮增量：正数向下滚，负数向上。\n'
      + '不是屏幕坐标；常见取值 600～1500。整页定位请用「滚动到指定高度位置」。',
    cursor_x:
      '可选。滚轮前先把光标移到该 X（视口像素）。\n'
      + '用于对准侧栏、表格、弹层等内部滚动条；不填则保持当前光标位置。',
    cursor_y:
      '可选。滚轮前先把光标移到该 Y（视口像素）；与光标 X 可只填一项，另一项默认视口中心。',
  },
  set_local_storage: {
    key:
      'LocalStorage 的键名（站点真实键，如 token、access_token）。\n'
      + 'BrickCore 本平台免登录常填 uStore 或 userInfo，值须为完整 JSON，不是纯 Token。',
    value:
      '写入的字符串。纯 Token 直接填；需要 JSON 时粘贴整段对象文本。\n'
      + '支持 ${{TOKEN}}。写完后请「刷新页面」或再打开业务页，否则 SPA 可能仍用旧内存态。',
  },
  set_session_storage: {
    key: 'SessionStorage 键名。关闭标签页后会清空，适合临时会话。须先打开目标域名页面。',
    value: '写入的字符串，支持 ${{变量}}。与 LocalStorage 用法相同，只是生命周期不同。',
  },
  add_cookies: {
    name: 'Cookie 名称，须与目标站一致（如 SESSION、sid）。',
    value: 'Cookie 值，支持 ${{变量}}。',
    domain:
      '可选。如 .example.com。与 url 二选一即可；domain 与 url 不要同时依赖。\n'
      + '都不填时，若已打开目标页，将使用当前页 URL。',
    path: 'Cookie 路径，默认 /。一般保持默认。',
    url:
      '可选。用完整 URL 声明 Cookie 作用域（如 https://example.com/）。\n'
      + '与 domain 二选一；已打开目标页时可留空自动推导。',
  },
  set_auth_token: {
    token:
      '鉴权凭证（JWT 或 access_token）。可写死或 ${{TOKEN}}。\n'
      + '不要在这里加 Bearer 前缀，前缀由下方「前缀」字段拼接。',
    header_name: 'HTTP 请求头名称，多数站点为 Authorization；少数为 X-Auth-Token 等。',
    header_prefix:
      '拼在 Token 前的前缀，默认 Bearer（最终形如 Authorization: Bearer xxx）。\n'
      + '目标站不要前缀时把本项清空。',
    storage_key:
      '可选。填了才会把「纯 Token 字符串」写入该 LocalStorage 键。\n'
      + '需要 JSON 整包登录态时，请改用「设置 LocalStorage」，不要填本项指望自动拼 JSON。',
  },
  save_storage_state: {
    path:
      '执行机本机文件路径（如 D:\\\\auth\\\\state.json）。\n'
      + '导出后可在环境「Web 启动登录态注入 → storage_state」填同一路径，下次开浏览器自动加载。',
  },
  switch_to_page: {
    tag: '可选。按页面标签名切换（与新建窗口时填写的 tag 对应）',
    index: '可选。标签页下标：0=第一个，-1=最新；回原页一般填 0',
    title: '可选。按网页标题精确匹配',
    url: '可选。按 URL 正则/子串匹配；与 index/title/tag 四选一即可，不必填',
  },
  close_page: {
    tag: '可选。不填则关闭当前页',
    index: '可选。按标签页下标关闭',
    title: '可选。按网页标题关闭',
    url: '可选。按 URL 匹配关闭；不必填',
  },
  wait_for_download: {
    save_path: '独立步骤有漏事件风险；更推荐在点击步骤高级配置里开启「等待文件下载」',
    var_name: '将下载路径写入变量（可选）',
  },
  accept_dialog: {
    prompt_text:
      '仅用于浏览器系统 prompt。本步只注册「下一步」的处理器；页面二次确认请用两步点击。',
  },
  dismiss_dialog: {},
  extract_response_field: {
    field: 'JSON 字段路径，如 data.id、items[0].name',
    url: '若需重新等待接口，填写 URL 匹配（可选）',
    var_name: '提取结果写入的变量名',
  },
  wait_for_element_text_change: {
    text: '初始文本（留空则取步骤开始时的当前文本）',
  },
  wait_for_element_text_stable: {
    stable_ms: '文本连续不变多少毫秒后视为稳定，默认 500',
  },
  wait_for_response: {
    url: '接口 URL 子串或正则，如 /api/user 或 login',
    method: 'HTTP 方法过滤，如 GET/POST（可选）',
    status: 'HTTP 状态码过滤，如 200（可选）',
  },
  click_by_image: {
    template: 'MinIO 对象键（可上传识别图）；固定 viewport 下匹配小图并点击',
    threshold: '相似度阈值 0.1～0.99，默认 0.8',
  },
  fill_by_image: {
    template: '输入框区域模板（建议截 placeholder 或整框）；匹配后点击并键盘输入',
    value: '要输入的文本，支持 ${{变量名}}',
    clear_first: '输入前是否先清空（Ctrl/Cmd+A 后 Backspace），默认是',
    threshold: '相似度阈值 0.1～0.99，默认 0.8',
  },
  wait_for_image: {
    template: '等待页面上出现与模板匹配的区域',
    threshold: '相似度阈值，默认 0.8',
  },
  kw_assert_image: {
    template: '断言当前页面能匹配到模板图像',
    threshold: '相似度阈值，默认 0.8',
  },
  kw_assert_image_not_exists: {
    template: '断言当前页面不能匹配到模板图像（如弹窗已关闭、图标已消失）',
    threshold: '相似度阈值，默认 0.8',
  },
  smart_step: {
    intent: '用自然语言描述本步要完成的操作，执行时将调用 AI Act 规划并执行',
  },
}

export function isAssertionMethod(method) {
  return ASSERTION_METHODS.has(method)
}

export function getOrderedVisibleParams(method, params = {}, options = {}) {
  const scope = options.scope || 'basic'
  const order = UI_STEP_PARAM_ORDER[method]
  if (!order) {
    if (scope === 'advanced') return {}
    return { ...params }
  }
  const advancedKeySet = new Set(getStepAdvancedParamKeys(method))
  const optionalDragKeys = new Set([
    'source_position_x',
    'source_position_y',
    'target_position_x',
    'target_position_y',
  ])
  const clickDownloadKeys = new Set(['save_path', 'var_name', 'download_timeout'])
  const clickDialogKeys = new Set(['dialog_timeout', 'prompt_text'])
  const postWaitKeys = new Set(['expected_selector', 'post_wait_state', 'wait_busy_after'])
  const preReadyKeys = new Set(['ready_selector', 'use_env_ready'])
  const result = {}
  for (const key of order) {
    if (scope === 'basic' && advancedKeySet.has(key)) continue
    if (scope === 'advanced' && !advancedKeySet.has(key)) continue
    if (
      (method === 'click_ele' || method === 'click_by_text')
      && clickDownloadKeys.has(key)
      && !params.wait_download
    ) {
      continue
    }
    if (
      (method === 'click_ele' || method === 'click_by_text')
      && clickDialogKeys.has(key)
      && !params.accept_dialog
      && !params.dismiss_dialog
    ) {
      continue
    }
    if (
      (method === 'click_ele' || method === 'click_by_text')
      && key === 'prompt_text'
      && !params.accept_dialog
    ) {
      continue
    }
    if (method === 'scroll_to_height' && key === 'height') {
      const pos = String(params.position || 'height').toLowerCase()
      if (['top', 'middle', 'bottom'].includes(pos)) continue
    }
    if (method === 'mouse_wheel') {
      const dir = String(params.direction || 'custom').toLowerCase()
      const preset = ['down', 'up', 'left', 'right'].includes(dir)
      if (key === 'amount' && !preset) continue
      if ((key === 'x' || key === 'y') && preset) continue
    }
    if (Object.prototype.hasOwnProperty.call(params, key)) {
      result[key] = params[key]
    } else if (preReadyKeys.has(key) && advancedKeySet.has(key)) {
      if (key === 'ready_selector') result[key] = ''
      else if (key === 'use_env_ready') result[key] = false
    } else if (postWaitKeys.has(key) && advancedKeySet.has(key)) {
      if (key === 'expected_selector') result[key] = ''
      else if (key === 'post_wait_state') result[key] = 'reappear'
      else if (key === 'wait_busy_after') result[key] = false
    } else if (method === 'scroll_to_height' && key === 'position') {
      result[key] = 'height'
    } else if (method === 'scroll_to_height' && key === 'height') {
      const pos = String(params.position || 'height').toLowerCase()
      result[key] = (pos === 'up' || pos === 'down') ? 600 : 0
    } else if (method === 'mouse_wheel' && key === 'direction') {
      result[key] = 'custom'
    } else if (method === 'mouse_wheel' && key === 'amount') {
      result[key] = 600
    } else if (method === 'mouse_wheel' && (key === 'x' || key === 'y')) {
      result[key] = key === 'y' ? 600 : 0
    } else if (method === 'mouse_wheel' && (key === 'cursor_x' || key === 'cursor_y')) {
      result[key] = ''
    } else if (
      isDragDropMethod(method)
      && optionalDragKeys.has(key)
    ) {
      result[key] = ''
    } else if (key === 'match_mode' && method === 'kw_assert_element_text') {
      result[key] = 'exact'
    } else if (
      (method === 'set_local_storage' || method === 'set_session_storage')
      && (key === 'key' || key === 'value')
    ) {
      result[key] = params[key] ?? ''
    } else if (key === 'wait_download' && (method === 'click_ele' || method === 'click_by_text')) {
      result[key] = params[key] ?? false
    } else if (
      (key === 'accept_dialog' || key === 'dismiss_dialog' || key === 'use_regex')
      && (method === 'click_ele' || method === 'click_by_text' || method === 'wait_for_url_contains')
    ) {
      result[key] = params[key] ?? false
    } else if (
      (method === 'click_ele' || method === 'click_by_text')
      && clickDownloadKeys.has(key)
      && params.wait_download
    ) {
      result[key] = key === 'download_timeout' ? (params[key] ?? 60000) : (params[key] ?? '')
    } else if (
      (method === 'click_ele' || method === 'click_by_text')
      && key === 'dialog_timeout'
      && (params.accept_dialog || params.dismiss_dialog)
    ) {
      result[key] = params[key] ?? 10000
    } else if (
      (method === 'click_ele' || method === 'click_by_text')
      && key === 'prompt_text'
      && params.accept_dialog
    ) {
      result[key] = params[key] ?? ''
    } else if (key === 'index' && order.includes('index')) {
      result[key] = params[key] ?? 1
    } else if (
      (key === 'source_index' || key === 'target_index')
      && order.includes(key)
    ) {
      result[key] = params[key] ?? 1
    } else if (key === 'order' && method === 'kw_assert_element_order') {
      result[key] = params[key] || 'before'
    } else if (
      (key === 'first_index' || key === 'second_index')
      && method === 'kw_assert_element_order'
    ) {
      result[key] = params[key] ?? 1
    }
  }
  return result
}

export function getParamLabel(method, key, fallbackLabel) {
  return (
    UI_STEP_PARAM_LABELS[method]?.[key]
    || ({
      ready_selector: '动作前就绪选择器',
      use_env_ready: '使用环境就绪选择器',
      expected_selector: '动作后等待选择器',
      post_wait_state: '动作后等待状态',
      wait_busy_after: '动作后再等忙碌遮罩',
    })[key]
    || fallbackLabel
    || key
  )
}

export function getParamTooltip(method, key) {
  const specific = UI_STEP_PARAM_TOOLTIPS[method]?.[key] || ''
  if (specific) return specific
  if (key === 'frame' && String(method || '').startsWith('frame_')) {
    return FRAME_LOCATOR_TOOLTIP
  }
  if (key === 'ready_selector') {
    return (
      '本步动作前额外等待的业务就绪点（如主表单已渲染）。\n'
      + '与环境「就绪选择器」独立；一般点击前默认只等忙碌遮罩，需要时再填。'
    )
  }
  if (key === 'use_env_ready') {
    return (
      '开启后，本步动作前也会等待环境配置的就绪选择器。\n'
      + '默认关闭，避免每次点击都被环境 ready 挡住。'
    )
  }
  return ''
}

/** 易误用步骤：新增/编辑弹窗内展示的使用说明 */
export const UI_STEP_USAGE_GUIDES = {
  accept_dialog: {
    title: '接受原生弹窗',
    type: 'warning',
    paragraphs: [
      '只处理浏览器系统弹窗（alert/confirm/prompt），不是页面自己画的二次确认框。',
      '本步只注册「下一步」处理器：请放在触发弹窗的点击之前；下一步未触发会自动清除。',
      '日常删除确认等页面弹窗：请拆成两步点击（点删除 → 点确定），不要用本步骤。',
    ],
    example:
      '系统 confirm：接受弹窗 → 点击触发按钮\n'
      + '页面 Dialog：点击删除 → 点击确定',
  },
  dismiss_dialog: {
    title: '取消原生弹窗',
    type: 'warning',
    paragraphs: [
      '只处理浏览器系统 confirm/prompt 的「取消」。',
      '放在触发点击之前；页面组件弹窗请另加一步点击「取消」。',
    ],
  },
  wait_for_download: {
    title: '等待下载',
    type: 'warning',
    paragraphs: [
      '独立步骤有时序风险；更推荐在「点击元素」→ 高级配置里开启「点击后等待文件下载」。',
      '本步仅对紧随下一步生效，未触发下载会自动清除。',
    ],
  },
  wait_for_url_contains: {
    title: '等待 URL 包含',
    type: 'info',
    paragraphs: [
      '默认按字面子串匹配（填 /dashboard 即可）。',
      '需要正则时再打开 use_regex，避免把普通路径当成正则一直等。',
    ],
  },
  set_local_storage: {
    title: '设置 LocalStorage',
    type: 'warning',
    paragraphs: [
      '须先「访问页面url」打开目标域名，否则无法写入同源存储。',
      '通用：键=站点真实键，值=纯 Token 字符串。',
      'BrickCore 本平台：键填 uStore（或 userInfo），值贴完整登录 JSON（含 token、isAuthenticated、userInfo.is_superuser）。',
      '写完后请「刷新页面」或再打开业务页（如 /#/dashboard），不要停在登录页；建议加断言确认已登录。',
    ],
    example:
      '打开 https://sut.example/\n'
      + '设置 LocalStorage：key=token，value=eyJ...\n'
      + '刷新 → 打开业务页 → 断言',
  },
  set_session_storage: {
    title: '设置 SessionStorage',
    type: 'info',
    paragraphs: [
      '与设置 LocalStorage 类似，但关闭标签页后会清空。',
      '须先打开目标域名页面再写入。',
    ],
  },
  set_auth_token: {
    title: '设置鉴权 Token',
    type: 'info',
    paragraphs: [
      '通用首选：写入请求头（默认 Authorization: Bearer <token>），LocalStorage 键可留空。',
      '若目标站还要把纯 Token 存到某个键，再填「同步写入 LocalStorage 键」（只写字符串）。',
      '需要 Cookie 或整份登录态：用「设置 Cookie」或「导出登录态」；需要 JSON 登录包：用「设置 LocalStorage」。',
    ],
    example:
      '打开目标域 → 设置鉴权Token（token + Bearer）→ 打开业务页 → 断言',
  },
  add_cookies: {
    title: '设置 Cookie',
    type: 'info',
    paragraphs: [
      '适合 Session Cookie 免登录。须提供 domain 或 url；已打开目标页时可都不填，自动用当前 URL。',
      '可与登录步骤片段、接口取 Cookie 配合；写完后打开业务页验证。',
    ],
    example:
      '打开 https://sut.example/\n'
      + '设置 Cookie：name=SESSION，value=xxx，domain=.example.com\n'
      + '打开业务页',
  },
  save_storage_state: {
    title: '导出登录态',
    type: 'info',
    paragraphs: [
      '把当前浏览器 Cookie/Storage 导出为 Playwright storage_state 文件（路径在执行机本机）。',
      '跨站点最省事的免登录：先正常登录一次 → 导出 → 环境「启动登录态」填同一路径，后续用例跳过登录 UI。',
    ],
    example:
      '登录成功后 → 导出登录态 path=D:\\\\auth\\\\state.json\n'
      + '环境启动登录态填写同一路径',
  },
  scroll_to_height: {
    title: '滚动到指定高度位置',
    type: 'info',
    paragraphs: [
      '会自动找页面主滚动区（含 SPA 内容容器）；相对上下滚不动时会改用鼠标滚轮。',
      '可选顶部 / 中间 / 底部，或相对向上、向下（距离建议 600～1500），或填写绝对高度。',
      '弹层、表格内部小滚动条仍请用「滚动到元素」。',
    ],
  },
  mouse_wheel: {
    title: '鼠标滚动',
    type: 'info',
    paragraphs: [
      '在光标位置派发滚轮事件：适合侧栏、表格、弹层等「鼠标指哪滚哪」的内部滚动条。',
      '与「滚动到指定高度位置」不同：本步不设置 scrollTop，只模拟滚轮；日常整页上下滚优先用后者。',
      '方向可选向下/向上/向左/向右（距离建议 600～1500）；需要斜向滚动时用「自定义」填 ΔX/ΔY。',
      '滚不到目标区时：先「移动鼠标」或填写光标 X/Y 对准该区域，再滚轮。',
    ],
    example:
      '整页下移：优先用「滚动到指定高度 → 相对向下」\n'
      + '表格内部下移：光标移到表格内 → 鼠标滚动「向下」600',
  },
  switch_to_page: {
    title: '切换页面',
    type: 'info',
    paragraphs: [
      '用于在多个标签页之间切换。tag / 顺序索引 / 标题 / URL 四选一即可，都不是必填。',
      '回最初打开的那页：顺序索引填 0，其余留空。',
      '切到刚新开的标签：优先用「切换到最新页面」，或索引填 -1。',
    ],
  },
  wait_for_response: {
    title: '等待接口响应',
    type: 'info',
    paragraphs: [
      '放在触发 Ajax 的操作之后，等待匹配 URL 的响应并缓存，供「提取接口响应字段」使用。',
    ],
    example:
      '1. 点击保存\n'
      + '2. 等待接口响应 { url: "/api/save" }\n'
      + '3. 提取接口响应字段 { field: "data.id", var_name: "new_id" }',
  },
  extract_response_field: {
    title: '提取接口响应字段',
    type: 'info',
    paragraphs: [
      '从最近一次「等待接口响应」的 JSON 中取值写入变量；也可用 url 让本步重新等待一次。',
    ],
  },
  click_ele: {
    title: '点击高级选项说明',
    type: 'info',
    paragraphs: [
      '日常二次确认（页面 Dialog）：拆成两步点击即可，不要开「原生弹窗」。',
      '浏览器系统弹窗（少见）：在高级配置里开「自动点确定/取消」。',
      '点下载/导出按钮：在高级配置里开「点击后等待文件下载」（不是上传文件）。',
      '慢站保存/查询/菜单：在高级配置填写「动作后等待选择器」（比仅靠忙碌遮罩更可靠）。',
    ],
  },
  click_by_text: {
    title: '按文本点击 — 高级说明',
    type: 'info',
    paragraphs: [
      '页面二次确认请两步点击；系统弹窗/文件下载选项在高级配置里。',
      'exact：是否精确匹配文本，默认模糊。',
      '慢站关键操作请填写「动作后等待选择器」。',
    ],
  },
  smart_click: {
    title: '智能点击',
    type: 'info',
    paragraphs: [
      '先消歧再点击：多候选打分，分差不足会失败，不会默认点第一个。',
      '填写顺序：要点谁 → 本步要做什么 →（同页重复时）在哪个区域 → 危险操作再配「点完后应看到」。',
      '后置失败只失败本步，不会换第二候选，也不会触发定位自愈。',
    ],
    example:
      '目标：新增\n意图：点击顶部工具栏新增\n区域：顶部工具栏\n后置：文本可见「创建」',
  },
  smart_fill: {
    title: '智能输入',
    type: 'info',
    paragraphs: [
      '与智能点击相同的消歧规则；同页多表单同 label 时请填「在哪个区域」。',
      '未配置后置时，执行侧默认校验输入框的值等于本次输入内容。',
    ],
    example:
      '目标：用户名\n意图：在创建弹窗填写登录名\n区域：创建用户弹窗\n内容：demo_user',
  },
  wait_for_clickable: {
    title: '等待元素可点击',
    type: 'info',
    paragraphs: [
      '轮询直到元素可见、enabled，且 trial click 通过（比仅「等待可见」更严）。',
      '适用于遮罩未消、按钮短暂 disabled 的场景。',
    ],
  },
  click_if_exists: {
    title: '若存在则点击',
    type: 'info',
    paragraphs: [
      '在超时内轮询 DOM：一直未出现则成功跳过。',
      '出现但不可见时：未勾选 force 则成功跳过；勾选 force 可强制点隐藏节点。',
      '偶发弹窗更推荐「若可见则点击」。默认超时 5 秒。',
    ],
  },
  click_if_visible: {
    title: '若可见则点击',
    type: 'info',
    paragraphs: [
      '在超时内等待元素可见；一直不可见则成功跳过，不失败。',
      '适合非必现弹窗关闭按钮等容错场景；默认超时 5 秒。force 仅用于可见但仍被遮挡时。',
    ],
  },
  fill_if_exists: {
    title: '若存在则输入',
    type: 'info',
    paragraphs: [
      '在超时内等待 DOM 出现后尝试输入；未出现或不可操作时成功跳过。',
      '默认超时 5 秒。需要「必须看见才填」时用「若可见则输入」。',
    ],
  },
  fill_if_visible: {
    title: '若可见则输入',
    type: 'info',
    paragraphs: [
      '在超时内等待元素可见后输入；一直不可见则成功跳过。',
      '与「若可见则点击」同一套容错语义；默认超时 5 秒。',
    ],
  },
}

export function getStepUsageGuide(method) {
  if (!method) return null
  return UI_STEP_USAGE_GUIDES[method] || null
}

export function isDragDropMethod(method) {
  return method === 'drag_and_drop' || method === 'frame_drag_and_drop'
}

export function isElementOrderMethod(method) {
  return method === 'kw_assert_element_order'
}
