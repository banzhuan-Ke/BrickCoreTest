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
  'kw_assert_attribute',
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
])

/** method -> 有序可见参数列表（未列出的 params 字段不展示） */
export const UI_STEP_PARAM_ORDER = {
  open_browser: ['browser_type'],
  open_url: ['url', 'wait_until'],
  scroll_to_height: ['height'],
  execute_script: ['script', 'args'],
  open_new_page: ['tag'],
  switch_to_page: ['tag', 'index', 'title', 'url'],
  close_page: ['tag', 'index', 'title', 'url'],
  save_page_img: ['name'],
  fill_value: ['locator', 'value'],
  click_ele: ['locator', 'index', 'force'],
  double_click_ele: ['locator', 'index', 'force'],
  clear_value: ['locator'],
  set_checked: ['locator'],
  hover: ['locator'],
  focus_element: ['locator'],
  select_option: ['locator', 'value'],
  type_value: ['locator', 'value'],
  drag_and_drop: ['start_selector', 'end_selector', 'source_position_x', 'source_position_y', 'target_position_x', 'target_position_y', 'timeout'],
  long_click_element: ['locator', 'delay'],
  upload_file: ['locator'],
  mouse_click: ['x', 'y', 'button', 'count'],
  move_mouse: ['x', 'y'],
  mouse_down: ['button'],
  mouse_up: ['button'],
  mouse_wheel: ['x', 'y'],
  press_key: ['key'],
  press_type: ['keys'],
  frame_fill_value: ['frame', 'locator', 'value'],
  frame_click_element: ['frame', 'locator', 'index', 'button', 'force'],
  frame_hover: ['frame', 'locator'],
  frame_focus_element: ['frame', 'locator'],
  frame_select_option: ['frame', 'locator', 'value'],
  frame_type_value: ['frame', 'locator', 'value'],
  frame_long_click_element: ['frame', 'locator', 'delay'],
  frame_drag_and_drop: ['frame', 'start_selector', 'end_selector', 'source_position_x', 'source_position_y', 'target_position_x', 'target_position_y', 'timeout'],
  set_default_timeout: ['timeout'],
  wait_for_time: ['timeout'],
  wait_for_element: ['locator'],
  kw_assert_page_title: ['title'],
  kw_assert_page_url: ['url'],
  kw_assert_value: ['locator', 'value'],
  kw_assert_element_text: ['locator', 'text', 'match_mode'],
  kw_assert_element_text_contains: ['locator', 'text'],
  kw_assert_text_contains: ['text'],
  kw_assert_attribute: ['locator', 'attr_name', 'value'],
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
}

/** method + paramKey -> 展示标签（覆盖通用标签） */
export const UI_STEP_PARAM_LABELS = {
  drag_and_drop: {
    source_position_x: '起始落点X(像素)',
    source_position_y: '起始落点Y(像素)',
    target_position_x: '目标落点X(像素)',
    target_position_y: '目标落点Y(像素)',
  },
  frame_drag_and_drop: {
    source_position_x: '起始落点X(像素)',
    source_position_y: '起始落点Y(像素)',
    target_position_x: '目标落点X(像素)',
    target_position_y: '目标落点Y(像素)',
  },
  kw_assert_page_title: { title: '预期标题' },
  kw_assert_page_url: { url: '预期URL' },
  kw_assert_value: { value: '预期value' },
  kw_assert_element_text: { text: '预期文本', match_mode: '匹配方式' },
  kw_assert_element_text_contains: { text: '预期包含文本' },
  kw_assert_text_contains: { text: '预期包含文本' },
  kw_assert_attribute: { value: '预期属性值', attr_name: '属性名称' },
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

/** method + paramKey -> 参数悬浮说明 */
export const UI_STEP_PARAM_TOOLTIPS = {
  drag_and_drop: DRAG_DROP_TOOLTIPS,
  frame_drag_and_drop: DRAG_DROP_TOOLTIPS,
  kw_assert_element_order: ELEMENT_ORDER_TOOLTIPS,
}

export function isAssertionMethod(method) {
  return ASSERTION_METHODS.has(method)
}

export function getOrderedVisibleParams(method, params = {}) {
  const order = UI_STEP_PARAM_ORDER[method]
  if (!order) return { ...params }
  const optionalDragKeys = new Set([
    'source_position_x',
    'source_position_y',
    'target_position_x',
    'target_position_y',
  ])
  const result = {}
  for (const key of order) {
    if (Object.prototype.hasOwnProperty.call(params, key)) {
      result[key] = params[key]
    } else if (
      isDragDropMethod(method)
      && optionalDragKeys.has(key)
    ) {
      result[key] = ''
    } else if (key === 'match_mode' && method === 'kw_assert_element_text') {
      result[key] = 'exact'
    } else if (key === 'index' && order.includes('index')) {
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
  return UI_STEP_PARAM_TOOLTIPS[method]?.[key] || ''
}

export function isDragDropMethod(method) {
  return method === 'drag_and_drop' || method === 'frame_drag_and_drop'
}

export function isElementOrderMethod(method) {
  return method === 'kw_assert_element_order'
}
