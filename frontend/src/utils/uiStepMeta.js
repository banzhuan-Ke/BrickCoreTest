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
  open_new_page: ['tag'],
  switch_to_page: ['tag', 'index', 'title', 'url'],
  close_page: ['tag', 'index', 'title', 'url'],
  save_page_img: ['name'],
  fill_value: ['locator', 'value', 'index'],
  click_ele: ['locator', 'index', 'force', 'expected_selector', 'post_wait_state', 'wait_busy_after', 'wait_download', 'save_path', 'var_name', 'download_timeout', 'accept_dialog', 'dismiss_dialog', 'dialog_timeout', 'prompt_text'],
  click_by_text: ['text', 'index', 'exact', 'force', 'expected_selector', 'post_wait_state', 'wait_busy_after', 'wait_download', 'save_path', 'var_name', 'download_timeout', 'accept_dialog', 'dismiss_dialog', 'dialog_timeout', 'prompt_text'],
  double_click_ele: ['locator', 'index', 'force', 'expected_selector', 'post_wait_state', 'wait_busy_after'],
  clear_value: ['locator', 'index'],
  set_checked: ['locator', 'index', 'expected_selector', 'post_wait_state', 'wait_busy_after'],
  hover: ['locator', 'index'],
  focus_element: ['locator', 'index'],
  select_option: ['locator', 'value', 'index', 'expected_selector', 'post_wait_state', 'wait_busy_after'],
  type_value: ['locator', 'value', 'index'],
  drag_and_drop: ['start_selector', 'end_selector', 'source_index', 'target_index', 'source_position_x', 'source_position_y', 'target_position_x', 'target_position_y', 'timeout', 'expected_selector', 'post_wait_state', 'wait_busy_after'],
  long_click_element: ['locator', 'delay', 'index', 'expected_selector', 'post_wait_state', 'wait_busy_after'],
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
  frame_click_element: ['frame', 'locator', 'index', 'button', 'force', 'expected_selector', 'post_wait_state', 'wait_busy_after'],
  frame_hover: ['frame', 'locator', 'index'],
  frame_focus_element: ['frame', 'locator', 'index'],
  frame_select_option: ['frame', 'locator', 'value', 'index', 'expected_selector', 'post_wait_state', 'wait_busy_after'],
  frame_type_value: ['frame', 'locator', 'value', 'index'],
  frame_long_click_element: ['frame', 'locator', 'delay', 'index', 'expected_selector', 'post_wait_state', 'wait_busy_after'],
  frame_drag_and_drop: ['frame', 'start_selector', 'end_selector', 'source_index', 'target_index', 'source_position_x', 'source_position_y', 'target_position_x', 'target_position_y', 'timeout', 'expected_selector', 'post_wait_state', 'wait_busy_after'],
  set_default_timeout: ['timeout'],
  wait_for_time: ['timeout'],
  wait_for_element: ['locator', 'index'],
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

/** 点击类：收进「高级配置」的参数（日常二次确认弹窗请拆两步点击，勿用这些） */
const POST_WAIT_PARAM_KEYS = ['expected_selector', 'post_wait_state', 'wait_busy_after']

export const UI_STEP_ADVANCED_PARAM_KEYS = {
  click_ele: [
    ...POST_WAIT_PARAM_KEYS,
    'wait_download', 'save_path', 'var_name', 'download_timeout',
    'accept_dialog', 'dismiss_dialog', 'dialog_timeout', 'prompt_text',
  ],
  click_by_text: [
    ...POST_WAIT_PARAM_KEYS,
    'wait_download', 'save_path', 'var_name', 'download_timeout',
    'accept_dialog', 'dismiss_dialog', 'dialog_timeout', 'prompt_text',
  ],
  double_click_ele: [...POST_WAIT_PARAM_KEYS],
  set_checked: [...POST_WAIT_PARAM_KEYS],
  select_option: [...POST_WAIT_PARAM_KEYS],
  long_click_element: [...POST_WAIT_PARAM_KEYS],
  drag_and_drop: [...POST_WAIT_PARAM_KEYS],
  frame_click_element: [...POST_WAIT_PARAM_KEYS],
  frame_select_option: [...POST_WAIT_PARAM_KEYS],
  frame_long_click_element: [...POST_WAIT_PARAM_KEYS],
  frame_drag_and_drop: [...POST_WAIT_PARAM_KEYS],
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
    expected_selector: '动作后等待选择器',
    post_wait_state: '动作后等待状态',
    wait_busy_after: '动作后再等忙碌遮罩',
  },
  double_click_ele: {
    expected_selector: '动作后等待选择器',
    post_wait_state: '动作后等待状态',
    wait_busy_after: '动作后再等忙碌遮罩',
  },
  set_checked: {
    expected_selector: '动作后等待选择器',
    post_wait_state: '动作后等待状态',
    wait_busy_after: '动作后再等忙碌遮罩',
  },
  select_option: {
    expected_selector: '动作后等待选择器',
    post_wait_state: '动作后等待状态',
    wait_busy_after: '动作后再等忙碌遮罩',
  },
  long_click_element: {
    expected_selector: '动作后等待选择器',
    post_wait_state: '动作后等待状态',
    wait_busy_after: '动作后再等忙碌遮罩',
  },
  frame_click_element: {
    expected_selector: '动作后等待选择器',
    post_wait_state: '动作后等待状态',
    wait_busy_after: '动作后再等忙碌遮罩',
  },
  frame_select_option: {
    expected_selector: '动作后等待选择器',
    post_wait_state: '动作后等待状态',
    wait_busy_after: '动作后再等忙碌遮罩',
  },
  frame_long_click_element: {
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
    expected_selector:
      '动作后的业务变化点，不要填页面上一直存在的表格壳/菜单/标题。\n'
      + '推荐：成功提示、加载完成后才出现的空态文案、结果计数变化对应节点。\n'
      + '查询/保存后列表刷新请用状态「先消失再出现」。',
    post_wait_state:
      'reappear（推荐）= 已可见则先等消失再等出现，避免抢跑；\n'
      + 'visible=仅等出现（常驻元素会立刻成功）；hidden=仅等消失',
    wait_busy_after: '额外再短探测环境忙碌遮罩；一般填「动作后等待选择器」即可',
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
  return UI_STEP_PARAM_LABELS[method]?.[key] || fallbackLabel || key
}

export function getParamTooltip(method, key) {
  const specific = UI_STEP_PARAM_TOOLTIPS[method]?.[key] || ''
  if (specific) return specific
  if (key === 'frame' && String(method || '').startsWith('frame_')) {
    return FRAME_LOCATOR_TOOLTIP
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
