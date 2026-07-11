/**
 * App 步骤参数展示元数据（与 AppActionGroup.js / app_keywords.py 对齐）
 */
import { allAppSteps, APP_DRIVER_MODE_OPTIONS, APP_LOCATOR_BY_OPTIONS, APP_WEBVIEW_LOCATOR_BY_OPTIONS } from '@/datas/AppActionGroup.js'

export const APP_METHODS = new Set(allAppSteps.map((item) => item.method))

/** method -> 有序可见参数列表（未列出的字段不展示） */
export const APP_STEP_PARAM_ORDER = {
  launch_app: ['app_id', 'stop'],
  launch_wechat: ['stop'],
  terminate_app: ['app_id'],
  clear_app: ['app_id'],
  install_app: ['app_path'],
  uninstall_app: ['app_id'],
  click_element: ['locator', 'locator_ref', 'timeout'],
  double_click_element: ['locator', 'locator_ref', 'timeout'],
  long_press_element: ['locator', 'locator_ref', 'duration', 'timeout'],
  input_text: ['locator', 'locator_ref', 'text', 'timeout'],
  clear_text: ['locator', 'locator_ref', 'timeout'],
  get_text: ['locator', 'locator_ref', 'timeout'],
  wait_element: ['locator', 'locator_ref', 'timeout'],
  wait_gone: ['locator', 'locator_ref', 'timeout'],
  wait_for_time: ['seconds'],
  swipe: ['direction'],
  scroll_to: ['locator', 'locator_ref'],
  assert_exists: ['locator', 'locator_ref', 'timeout'],
  assert_not_exists: ['locator', 'locator_ref', 'timeout'],
  assert_image_exists: ['locator', 'locator_ref', 'timeout'],
  assert_image_not_exists: ['locator', 'locator_ref', 'timeout'],
  assert_text: ['locator', 'locator_ref', 'text', 'timeout'],
  assert_text_contains: ['locator', 'locator_ref', 'text', 'timeout'],
  extract_text: ['locator', 'locator_ref', 'var_name', 'timeout'],
  press_key: ['key'],
  open_url: ['url'],
  screenshot: ['name'],
  switch_webview: ['page_index', 'package', 'url'],
  switch_chrome: ['page_index', 'url'],
  switch_native: [],
}

/** 必填参数（与 backend APP_REQUIRED_PARAMS 对齐） */
export const APP_REQUIRED_PARAMS = {
  launch_app: ['app_id'],
  terminate_app: ['app_id'],
  clear_app: ['app_id'],
  install_app: ['app_path'],
  uninstall_app: ['app_id'],
  click_element: ['locator'],
  double_click_element: ['locator'],
  long_press_element: ['locator'],
  input_text: ['locator', 'text'],
  clear_text: ['locator'],
  get_text: ['locator'],
  wait_element: ['locator'],
  wait_gone: ['locator'],
  assert_exists: ['locator'],
  assert_not_exists: ['locator'],
  assert_image_exists: ['locator'],
  assert_image_not_exists: ['locator'],
  assert_text: ['locator', 'text'],
  assert_text_contains: ['locator', 'text'],
  extract_text: ['locator', 'var_name'],
  press_key: ['key'],
  open_url: ['url'],
  screenshot: ['name'],
  wait_for_time: ['seconds'],
}

export const APP_STEP_PARAM_LABELS = {
  locator: '元素定位',
  locator_ref: '元素库引用',
  seconds: '等待时间(秒)',
  timeout: '超时时间(秒)',
  app_id: '应用包名',
  app_path: 'APK 路径',
  duration: '长按时长(秒)',
  var_name: '变量名',
  stop: '启动前先停止',
  text: '文本内容',
  key: '按键',
  direction: '滑动方向',
  url: '链接地址',
  name: '截图名称',
  page_index: 'WebView/Chrome 页面索引',
  package: '限定包名（WebView）',
}

export const APP_STEP_PARAM_TOOLTIPS = {
  locator_ref: '选择后自动同步到「元素定位」，仍可手动修改；保存时若已改定位则仅保留定位内容。',
  stop: '勾选后启动前会先 force-stop 该应用',
  timeout: '等待元素出现/点击等操作的最长秒数',
  seconds: '固定休眠秒数，不做元素检测',
  direction: '在屏幕上滑动，常用于翻页或下拉刷新',
  page_index: '与元素探查中「可调试页面」下拉索引一致，从 0 开始',
  url: '可选，按 URL 片段匹配 Tab（Chrome/WebView 均可用）',
}

export const APP_SELECT_OPTIONS = {
  direction: [
    { label: '向上', value: 'up' },
    { label: '向下', value: 'down' },
    { label: '向左', value: 'left' },
    { label: '向右', value: 'right' },
  ],
  key: [
    { label: 'Home', value: 'home' },
    { label: '返回', value: 'back' },
    { label: '最近任务', value: 'recent' },
    { label: '菜单', value: 'menu' },
    { label: '电源', value: 'power' },
  ],
}

/** App 条件分支支持的条件类型（与 Runner _eval_branch_condition 对齐） */
export const APP_CONDITION_TYPES = [
  { label: '元素存在', value: 'element_exist' },
  { label: '元素文本包含', value: 'element_text_contains' },
]

export function isAppMethod(method) {
  return APP_METHODS.has(method)
}

export const APP_LOCATOR_CONTEXT_NATIVE = 'native'

const APP_ID_PARAM_METHODS = new Set(['launch_app', 'terminate_app', 'clear_app', 'uninstall_app'])

/** 从项目全局变量 / 用例步骤 / 本地缓存解析默认应用包名 */
export function getProjectDefaultAppId(projectInfo, steps = []) {
  const gv = projectInfo?.global_vars
  if (gv && typeof gv === 'object') {
    for (const key of ['app', 'app_id', 'appId', 'package', 'app_package']) {
      const val = gv[key]
      if (val != null && String(val).trim()) {
        return String(val).trim()
      }
    }
  }
  for (const step of steps || []) {
    if (!APP_ID_PARAM_METHODS.has(step?.method)) continue
    const appId = step?.params?.app_id
    if (appId != null && String(appId).trim()) {
      return String(appId).trim()
    }
  }
  try {
    const projectId = projectInfo?.id
    if (projectId) {
      const cached = localStorage.getItem(`app_default_package_${projectId}`)
      if (cached && cached.trim()) return cached.trim()
    }
  } catch {
    /* ignore */
  }
  return ''
}

export function rememberProjectDefaultAppId(projectId, appId) {
  if (!projectId || appId == null || !String(appId).trim()) return
  try {
    localStorage.setItem(`app_default_package_${projectId}`, String(appId).trim())
  } catch {
    /* ignore */
  }
}

export function applyDefaultAppIdToStepParams(method, params, projectInfo, steps = []) {
  if (!params || !APP_ID_PARAM_METHODS.has(method)) return params
  if (params.app_id != null && String(params.app_id).trim()) return params
  const defaultAppId = getProjectDefaultAppId(projectInfo, steps)
  if (!defaultAppId) return params
  return { ...params, app_id: defaultAppId }
}

export function prepareAppLocatorForEdit(locator) {
  const loc = normalizeAppLocator(locator)
  if (!loc.context || loc.context === APP_LOCATOR_CONTEXT_NATIVE) {
    loc.context = APP_LOCATOR_CONTEXT_NATIVE
  }
  return loc
}

export function serializeAppLocatorForSave(locator) {
  const loc = normalizeAppLocator(locator)
  if (!loc.context || loc.context === APP_LOCATOR_CONTEXT_NATIVE) {
    delete loc.context
  }
  return loc
}

export function defaultAppLocator() {
  return { by: 'resource_id', value: '', index: 1, context: APP_LOCATOR_CONTEXT_NATIVE }
}

export function normalizeAppLocator(locator) {
  if (locator && typeof locator === 'object' && locator.by !== undefined) {
    if (String(locator.by).toLowerCase() === 'image') {
      return {
        by: 'image',
        value: locator.value ?? '',
        threshold: locator.threshold ?? 0.8,
        rgb: !!locator.rgb,
        ...(locator.record_pos ? { record_pos: locator.record_pos } : {}),
        ...(locator.resolution ? { resolution: locator.resolution } : {}),
        ...(locator.target_pos ? { target_pos: locator.target_pos } : {}),
      }
    }
    const normalized = {
      by: locator.by || 'resource_id',
      value: locator.value ?? '',
      index: locator.index ?? 1,
    }
    if (locator.context) {
      normalized.context = locator.context
    } else if (locator.by && locator.by !== 'image') {
      normalized.context = APP_LOCATOR_CONTEXT_NATIVE
    }
    if (isWebviewLocator(normalized)) {
      if (locator.page_index != null) normalized.page_index = locator.page_index
      if (locator.devtools_source) normalized.devtools_source = locator.devtools_source
    }
    return normalized
  }
  return defaultAppLocator()
}

export function isWebviewLocator(locator) {
  const ctx = String(locator?.context || '').toLowerCase()
  if (ctx === 'webview') return true
  if (ctx === APP_LOCATOR_CONTEXT_NATIVE || ctx === 'native') return false
  return ['css', 'id'].includes(String(locator?.by || ''))
}

export function isImageLocator(locator) {
  return String(locator?.by || '').toLowerCase() === 'image'
}

export function getAppLocatorByOptions(locator) {
  if (isWebviewLocator(locator)) {
    return APP_WEBVIEW_LOCATOR_BY_OPTIONS
  }
  return APP_LOCATOR_BY_OPTIONS
}

export function isAppLocatorFilled(locator) {
  const loc = normalizeAppLocator(locator)
  if (isImageLocator(loc)) {
    return !!String(loc.value ?? '').trim()
  }
  return !!(String(loc.by || '').trim() && String(loc.value ?? '').trim())
}

export function getAppOrderedVisibleParams(method, params = {}) {
  const order = APP_STEP_PARAM_ORDER[method]
  if (!order) return { ...params }
  const result = {}
  for (const key of order) {
    if (key === 'locator') {
      result[key] = normalizeAppLocator(params.locator)
      continue
    }
    if (Object.prototype.hasOwnProperty.call(params, key)) {
      result[key] = params[key]
    } else if (key === 'locator_ref') {
      result[key] = params[key] ?? ''
    } else if (key === 'seconds' && method === 'wait_for_time') {
      result[key] = params[key] ?? 2
    } else if (key === 'timeout') {
      result[key] = params[key] ?? 10
    } else if (key === 'duration' && method === 'long_press_element') {
      result[key] = params[key] ?? 1
    } else if (key === 'direction' && method === 'swipe') {
      result[key] = params[key] || 'up'
    } else if (key === 'key' && method === 'press_key') {
      result[key] = params[key] || 'home'
    } else if (key === 'name' && method === 'screenshot') {
      result[key] = params[key] || 'screenshot'
    } else if (key === 'stop' && (method === 'launch_app' || method === 'launch_wechat')) {
      result[key] = !!params[key]
    } else if (key === 'app_id' && APP_ID_PARAM_METHODS.has(method)) {
      result[key] = params[key] ?? ''
    }
  }
  return result
}

export function getAppParamLabel(method, key, fallbackLabel) {
  return APP_STEP_PARAM_LABELS[key] || fallbackLabel || key
}

export function getAppParamTooltip(method, key) {
  return APP_STEP_PARAM_TOOLTIPS[key] || ''
}

export function isAppRequiredParam(method, key) {
  return (APP_REQUIRED_PARAMS[method] || []).includes(key)
}

export function getAppSelectOptions(key) {
  return APP_SELECT_OPTIONS[key] || []
}

function collectStepLocators(steps, out = [], elementMap = null) {
  if (!Array.isArray(steps)) return out
  for (const step of steps) {
    const params = step.params || {}
    if (params.locator) out.push(params.locator)
    const ref = (params.locator_ref || '').trim()
    if (ref && elementMap && elementMap[ref]?.locator) {
      out.push(elementMap[ref].locator)
    }
    const branches = step.branches || params.branches
    if (Array.isArray(branches)) {
      for (const branch of branches) {
        const cond = branch?.condition || {}
        const loc = cond.locator
        if (loc) out.push(loc)
        const ref = (cond.locator_ref || '').trim()
        if (ref && elementMap && elementMap[ref]?.locator) {
          out.push(elementMap[ref].locator)
        }
        collectStepLocators(branch?.steps, out, elementMap)
      }
    }
  }
  return out
}

/** driver_mode 显示名 */
export function appDriverModeLabel(mode) {
  const found = APP_DRIVER_MODE_OPTIONS?.find?.((o) => o.value === mode)
  return found?.label || mode || '—'
}

/** 校验用例 driver_mode 与 H5/图像定位器是否匹配，返回错误文案或 null */
export function validateCaseDriverMode(driverMode, steps = [], elementOptions = []) {
  const elementMap = Object.fromEntries(
    (elementOptions || []).filter((e) => e?.name).map((e) => [e.name, e])
  )
  const locators = collectStepLocators(steps, [], elementMap)
  const hasWebview = locators.some(isWebviewLocator)
  const hasImage = locators.some(isImageLocator)
  if (hasWebview && !['hybrid_web', 'mobile_chrome'].includes(driverMode)) {
    return '用例包含 H5/WebView 定位，驱动模式须设为「混合 WebView(hybrid_web)」或「手机 Chrome(mobile_chrome)」'
  }
  if (hasImage && driverMode === 'native') {
    return '用例包含图像识别定位，驱动模式不能为「仅控件(native)」，请设为 hybrid 或 vision'
  }
  for (const loc of locators) {
    if (!isWebviewLocator(loc)) continue
    const src = String(loc.devtools_source || '').trim().toLowerCase()
    if (src === 'chrome' && driverMode === 'hybrid_web') {
      return '元素 H5 来源为 Chrome，驱动模式须为「手机 Chrome(mobile_chrome)」'
    }
    if (src === 'webview' && driverMode === 'mobile_chrome') {
      return '元素 H5 来源为 App WebView，驱动模式须为「混合 WebView(hybrid_web)」'
    }
  }
  return null
}

/** 校验条件分支（App） */
export function validateAppBranchConditions(branches = []) {
  if (!Array.isArray(branches)) return null
  for (const branch of branches) {
    const cond = branch?.condition
    if (!cond || cond.type === 'else') continue
    const name = branch.name || '未命名'
    if (['element_exist', 'element_text_contains', 'element_visible', 'element_text_equals'].includes(cond.type)) {
      if (typeof cond.locator === 'object') {
        if (cond.type === 'element_text_contains' && isImageLocator(cond.locator)) {
          return `条件分支「${name}」图像定位不支持文本包含判断`
        }
        if (!isAppLocatorFilled(cond.locator)) {
          return `条件分支「${name}」请填写完整元素定位`
        }
        if (isImageLocator(cond.locator)) {
          const th = cond.locator.threshold
          if (th != null && (Number(th) <= 0 || Number(th) > 1)) {
            return `条件分支「${name}」图像阈值须在 0~1 之间`
          }
        }
      }
      if (typeof cond.locator === 'string' && !String(cond.locator || '').trim()) {
        return `条件分支「${name}」请填写元素定位`
      }
    }
    if (['element_text_contains', 'element_text_equals'].includes(cond.type) && !String(cond.expected_value || '').trim()) {
      return `条件分支「${name}」请填写预期文本`
    }
  }
  return null
}

/** 保存前校验 App 步骤参数，返回错误文案或 null */
export function validateAppStepParams(method, params = {}) {
  const ref = (params.locator_ref || '').trim()
  if (ref) {
    return null
  }
  const required = APP_REQUIRED_PARAMS[method] || []
  for (const key of required) {
    if (key === 'locator') {
      if (!isAppLocatorFilled(params.locator)) {
        if (isImageLocator(params.locator)) {
          return '请上传识别小图'
        }
        return '请填写元素定位（定位方式 + 定位值）'
      }
      if (isImageLocator(params.locator)) {
        const th = params.locator.threshold
        if (th != null && (Number(th) <= 0 || Number(th) > 1)) {
          return '图像相似度阈值须在 0~1 之间'
        }
      }
      continue
    }
    const value = params[key]
    if (value === null || value === undefined || (typeof value === 'string' && !value.trim())) {
      return `请填写${APP_STEP_PARAM_LABELS[key] || key}`
    }
  }
  return null
}
