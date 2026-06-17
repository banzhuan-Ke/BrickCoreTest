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
  drag_and_drop: ['start_selector', 'end_selector'],
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
  frame_drag_and_drop: ['frame', 'start_selector', 'end_selector'],
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
  extract_text: ['locator', 'var_name', 'index'],
  extract_attribute: ['locator', 'attr_name', 'var_name', 'index'],
}

/** method + paramKey -> 展示标签（覆盖通用标签） */
export const UI_STEP_PARAM_LABELS = {
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
}

export function isAssertionMethod(method) {
  return ASSERTION_METHODS.has(method)
}

export function getOrderedVisibleParams(method, params = {}) {
  const order = UI_STEP_PARAM_ORDER[method]
  if (!order) return { ...params }
  const result = {}
  for (const key of order) {
    if (Object.prototype.hasOwnProperty.call(params, key)) {
      result[key] = params[key]
    } else if (key === 'match_mode' && method === 'kw_assert_element_text') {
      result[key] = 'exact'
    } else if (key === 'index' && order.includes('index')) {
      result[key] = params[key] ?? 1
    }
  }
  return result
}

export function getParamLabel(method, key, fallbackLabel) {
  return UI_STEP_PARAM_LABELS[method]?.[key] || fallbackLabel || key
}
