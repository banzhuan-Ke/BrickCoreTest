/**
 * Web 用例描述：录制 / AI 优化共用（方案 C：单字段 description）
 */

import { flattenGlobalVars } from './globalVars.js'

const VAR_PATTERN = /\$\{\{([^}]+)\}\}/g

/** 打开录制或 AI 优化时，解析用例描述上下文 */
export function resolveCaseDescriptionForContext(caseInfo) {
  const desc = (caseInfo?.description || '').trim()
  if (desc) return desc.slice(0, 4000)
  const name = (caseInfo?.name || '').trim()
  if (name) return `【用例】${name}`.slice(0, 4000)
  return ''
}

/** 从步骤中提取首个 open_url，供录制起始页预填 */
export function extractOpenUrlFromSteps(steps) {
  const list = steps || []
  const hit = list.find((s) => s?.method === 'open_url' && s?.params?.url)
  return (hit?.params?.url || '').trim()
}

/** 环境 global_vars 中 Web 默认起始 URL 的保留键 */
export const ENV_DEFAULT_START_URL_KEY = '__default_start_url'
export const ENV_DEFAULT_PERF_WORKER_ID_KEY = '__default_perf_worker_id'
export const UI_TIMEOUT_SCALE_KEY = '__ui_timeout_scale'
export const UI_NAV_WAIT_UNTIL_KEY = '__ui_nav_wait_until'
export const UI_BUSY_SELECTORS_KEY = '__ui_busy_selectors'
export const UI_READY_SELECTOR_KEY = '__ui_ready_selector'
export const UI_READINESS_RETRY_KEY = '__ui_readiness_retry'
export const UI_BUSY_APPEAR_PROBE_MS_KEY = '__ui_busy_appear_probe_ms'
export const UI_ACTION_SETTLE_MS_KEY = '__ui_action_settle_ms'
export const UI_ACTION_SETTLE_QUIET_MS_KEY = '__ui_action_settle_quiet_ms'
export const UI_AUTH_INJECT_KEY = '__ui_auth_inject'
export const UI_STORAGE_STATE_KEY = '__ui_storage_state'
export const UI_AUTH_PROFILES_KEY = '__ui_auth_profiles'
/** 总开关：false 时保留配置但不下发注入 */
export const UI_AUTH_ENABLED_KEY = '__ui_auth_enabled'

const UI_EXEC_RESERVED_KEYS = [
  ENV_DEFAULT_PERF_WORKER_ID_KEY,
  UI_TIMEOUT_SCALE_KEY,
  UI_NAV_WAIT_UNTIL_KEY,
  UI_BUSY_SELECTORS_KEY,
  UI_READY_SELECTOR_KEY,
  UI_READINESS_RETRY_KEY,
  UI_BUSY_APPEAR_PROBE_MS_KEY,
  UI_ACTION_SETTLE_MS_KEY,
  UI_ACTION_SETTLE_QUIET_MS_KEY,
  UI_AUTH_INJECT_KEY,
  UI_STORAGE_STATE_KEY,
  UI_AUTH_PROFILES_KEY,
  UI_AUTH_ENABLED_KEY,
]

export const DEFAULT_UI_TIMEOUT_SCALE = 1
export const DEFAULT_UI_NAV_WAIT_UNTIL = 'domcontentloaded'
export const DEFAULT_UI_READINESS_RETRY = 0
export const DEFAULT_UI_BUSY_APPEAR_PROBE_MS = 800
export const DEFAULT_UI_ACTION_SETTLE_MS = 0
export const DEFAULT_UI_ACTION_SETTLE_QUIET_MS = 300
export const ALLOWED_UI_NAV_WAIT_UNTIL = ['commit', 'domcontentloaded', 'load', 'networkidle']

export function getEnvDefaultStartUrl(globalVars) {
  const gv = globalVars && typeof globalVars === 'object' ? globalVars : {}
  const raw = gv[ENV_DEFAULT_START_URL_KEY]
  if (raw && typeof raw === 'object' && 'value' in raw) {
    return String(raw.value || '').trim()
  }
  return String(raw || '').trim()
}

export function getEnvDefaultPerfWorkerId(globalVars) {
  const gv = globalVars && typeof globalVars === 'object' ? globalVars : {}
  const raw = gv[ENV_DEFAULT_PERF_WORKER_ID_KEY]
  const val = raw && typeof raw === 'object' && 'value' in raw ? raw.value : raw
  const n = Number(val)
  return Number.isInteger(n) && n > 0 ? n : null
}

export function mergeEnvDefaultPerfWorkerId(globalVars, workerId) {
  const gv = globalVars && typeof globalVars === 'object' ? { ...globalVars } : {}
  const n = Number(workerId)
  if (Number.isInteger(n) && n > 0) {
    gv[ENV_DEFAULT_PERF_WORKER_ID_KEY] = n
  } else {
    delete gv[ENV_DEFAULT_PERF_WORKER_ID_KEY]
  }
  return gv
}

export function getProjectDefaultStartUrl(projectInfo) {
  const ai = projectInfo?.global_vars?.ai_settings
  return String(ai?.default_start_url || '').trim()
}

export function containsUnresolvedTemplate(text) {
  const s = String(text || '')
  return s.includes('${{') || s.includes('${')
}

export function substituteVariablesInText(text, variables) {
  const raw = String(text || '')
  if (!raw || !raw.includes('${{')) return raw
  const vars = variables && typeof variables === 'object' ? variables : {}
  return raw.replace(VAR_PATTERN, (match, key) => {
    const k = String(key || '').trim()
    if (Object.prototype.hasOwnProperty.call(vars, k)) {
      return String(vars[k] ?? '')
    }
    return match
  })
}

/** 构建 URL 变量替换上下文（项目 + 环境 global_vars，与后端 merge 顺序近似） */
export function buildStartUrlVariables(env, projectInfo = null) {
  const vars = {}
  if (projectInfo?.global_vars) {
    Object.assign(vars, flattenGlobalVars(projectInfo.global_vars))
  }
  if (env?.global_vars) {
    Object.assign(vars, flattenGlobalVars(env.global_vars))
  }
  const host = String(env?.host || '').trim()
  if (host) {
    vars.Base_url = host
    if (!vars.host) vars.host = host
  }
  return vars
}

/**
 * 校验 default_start_url 存储值（与后端 start_url.validate_default_start_url 对齐）
 * @returns {{ ok: boolean, error?: string, normalized?: string }}
 */
export function validateDefaultStartUrl(url) {
  const u = String(url || '').trim()
  if (!u) return { ok: true, normalized: '' }
  if (u.length > 500) return { ok: false, error: '默认起始 URL 长度不能超过 500 字符' }
  if (/\s/.test(u)) return { ok: false, error: '默认起始 URL 不能包含空格' }
  if (u.includes('${{')) return { ok: true, normalized: u }
  if (!/^https?:\/\//i.test(u)) {
    return { ok: false, error: '默认起始 URL 须以 http:// 或 https:// 开头，或使用 ${{变量名}} 模板' }
  }
  return { ok: true, normalized: u }
}

function resolveRawDefaultStartUrl({ steps, envId = null, envList = [], projectInfo = null } = {}) {
  const fromSteps = extractOpenUrlFromSteps(steps)
  if (fromSteps) return { raw: fromSteps, env: null }

  const env = envId != null
    ? (envList || []).find((e) => e.id === envId)
    : (envList || [])[0] || null
  const fromEnv = env ? getEnvDefaultStartUrl(env.global_vars) : ''
  if (fromEnv) return { raw: fromEnv, env }

  const fromProject = getProjectDefaultStartUrl(projectInfo)
  if (fromProject) return { raw: fromProject, env }

  const host = (env?.host || '').trim()
  if (!host) return { raw: '', env: env }
  const fallback = /^https?:\/\//i.test(host) ? host : `https://${host}`
  return { raw: fallback, env: env }
}

/**
 * 解析 Web 录制/调试默认起始 URL（含 ${{var}} 替换，与后端 debug 行为对齐）
 * envId 为空时使用 envList[0]；不绑定「变量插入参考环境」
 */
export function resolveDefaultStartUrl({
  steps,
  envId = null,
  envList = [],
  projectInfo = null,
  resolveVariables = true,
} = {}) {
  const { raw, env } = resolveRawDefaultStartUrl({ steps, envId, envList, projectInfo })
  if (!raw) return ''
  if (!resolveVariables) return raw

  const variables = buildStartUrlVariables(env, projectInfo)
  const resolved = substituteVariablesInText(raw, variables)
  if (containsUnresolvedTemplate(resolved)) return ''
  return resolved
}

/** 从 global_vars 中剥离保留键，供 GlobalVarsEditor 展示 */
export function globalVarsForEditor(globalVars) {
  const gv = globalVars && typeof globalVars === 'object' ? { ...globalVars } : {}
  delete gv[ENV_DEFAULT_START_URL_KEY]
  for (const k of UI_EXEC_RESERVED_KEYS) {
    delete gv[k]
  }
  return gv
}

/** 合并默认起始 URL 到 global_vars 保存 payload */
export function mergeEnvDefaultStartUrl(globalVars, defaultStartUrl) {
  const check = validateDefaultStartUrl(defaultStartUrl)
  if (!check.ok) {
    throw new Error(check.error || '默认起始 URL 无效')
  }
  const gv = globalVars && typeof globalVars === 'object' ? { ...globalVars } : {}
  const url = check.normalized || ''
  if (url) {
    gv[ENV_DEFAULT_START_URL_KEY] = url
  } else {
    delete gv[ENV_DEFAULT_START_URL_KEY]
  }
  return gv
}

function _plainReservedValue(raw) {
  if (raw && typeof raw === 'object' && !Array.isArray(raw) && 'value' in raw) {
    return raw.value
  }
  return raw
}

export function getEnvUiTimeoutScale(globalVars) {
  const raw = _plainReservedValue(
    globalVars && typeof globalVars === 'object' ? globalVars[UI_TIMEOUT_SCALE_KEY] : undefined
  )
  if (raw === null || raw === undefined || raw === '') return DEFAULT_UI_TIMEOUT_SCALE
  const n = Number(raw)
  if (!Number.isFinite(n)) return DEFAULT_UI_TIMEOUT_SCALE
  return Math.min(5, Math.max(0.5, n))
}

export function getEnvUiNavWaitUntil(globalVars) {
  const raw = _plainReservedValue(
    globalVars && typeof globalVars === 'object' ? globalVars[UI_NAV_WAIT_UNTIL_KEY] : undefined
  )
  const s = String(raw || '').trim().toLowerCase()
  if (ALLOWED_UI_NAV_WAIT_UNTIL.includes(s)) return s
  return DEFAULT_UI_NAV_WAIT_UNTIL
}

export function getEnvUiBusySelectorsText(globalVars) {
  const raw = _plainReservedValue(
    globalVars && typeof globalVars === 'object' ? globalVars[UI_BUSY_SELECTORS_KEY] : undefined
  )
  if (Array.isArray(raw)) {
    return raw.map((x) => String(x || '').trim()).filter(Boolean).join('\n')
  }
  return String(raw || '').replace(/\r\n/g, '\n').replace(/\r/g, '\n').trim()
}

export function getEnvUiReadySelector(globalVars) {
  const raw = _plainReservedValue(
    globalVars && typeof globalVars === 'object' ? globalVars[UI_READY_SELECTOR_KEY] : undefined
  )
  return String(raw || '').trim()
}

export function getEnvUiReadinessRetry(globalVars) {
  const raw = _plainReservedValue(
    globalVars && typeof globalVars === 'object' ? globalVars[UI_READINESS_RETRY_KEY] : undefined
  )
  if (raw === null || raw === undefined || raw === '') return DEFAULT_UI_READINESS_RETRY
  const n = Number(raw)
  if (!Number.isFinite(n)) return DEFAULT_UI_READINESS_RETRY
  return Math.min(3, Math.max(0, Math.trunc(n)))
}

export function getEnvUiBusyAppearProbeMs(globalVars) {
  const raw = _plainReservedValue(
    globalVars && typeof globalVars === 'object' ? globalVars[UI_BUSY_APPEAR_PROBE_MS_KEY] : undefined
  )
  if (raw === null || raw === undefined || raw === '') return DEFAULT_UI_BUSY_APPEAR_PROBE_MS
  const n = Number(raw)
  if (!Number.isFinite(n)) return DEFAULT_UI_BUSY_APPEAR_PROBE_MS
  return Math.min(5000, Math.max(0, Math.trunc(n)))
}

export function getEnvUiActionSettleMs(globalVars) {
  const raw = _plainReservedValue(
    globalVars && typeof globalVars === 'object' ? globalVars[UI_ACTION_SETTLE_MS_KEY] : undefined
  )
  if (raw === null || raw === undefined || raw === '') return DEFAULT_UI_ACTION_SETTLE_MS
  const n = Number(raw)
  if (!Number.isFinite(n)) return DEFAULT_UI_ACTION_SETTLE_MS
  return Math.min(30000, Math.max(0, Math.trunc(n)))
}

export function getEnvUiActionSettleQuietMs(globalVars) {
  const raw = _plainReservedValue(
    globalVars && typeof globalVars === 'object' ? globalVars[UI_ACTION_SETTLE_QUIET_MS_KEY] : undefined
  )
  if (raw === null || raw === undefined || raw === '') return DEFAULT_UI_ACTION_SETTLE_QUIET_MS
  const n = Number(raw)
  if (!Number.isFinite(n)) return DEFAULT_UI_ACTION_SETTLE_QUIET_MS
  return Math.min(5000, Math.max(0, Math.trunc(n)))
}

/**
 * 合并 UI 慢站策略到 global_vars
 * @returns {{ ok: true, globalVars: object } | { ok: false, error: string }}
 */
export function mergeEnvUiExecStrategy(
  globalVars,
  {
    timeoutScale,
    navWaitUntil,
    busySelectorsText,
    readySelector,
    readinessRetry,
    busyAppearProbeMs,
    actionSettleMs,
    actionSettleQuietMs,
  } = {}
) {
  const gv = globalVars && typeof globalVars === 'object' ? { ...globalVars } : {}

  let scale = Number(timeoutScale)
  if (!Number.isFinite(scale)) scale = DEFAULT_UI_TIMEOUT_SCALE
  if (scale < 0.5 || scale > 5) {
    return { ok: false, error: 'UI 超时倍率须在 0.5–5 之间' }
  }
  if (Math.abs(scale - DEFAULT_UI_TIMEOUT_SCALE) < 1e-9) {
    delete gv[UI_TIMEOUT_SCALE_KEY]
  } else {
    gv[UI_TIMEOUT_SCALE_KEY] = Math.round(scale * 1000) / 1000
  }

  const wait = String(navWaitUntil || DEFAULT_UI_NAV_WAIT_UNTIL).trim().toLowerCase()
  if (!ALLOWED_UI_NAV_WAIT_UNTIL.includes(wait)) {
    return { ok: false, error: '导航等待须为 commit / domcontentloaded / load / networkidle 之一' }
  }
  if (wait === DEFAULT_UI_NAV_WAIT_UNTIL) {
    delete gv[UI_NAV_WAIT_UNTIL_KEY]
  } else {
    gv[UI_NAV_WAIT_UNTIL_KEY] = wait
  }

  const lines = String(busySelectorsText || '')
    .replace(/\r\n/g, '\n')
    .replace(/\r/g, '\n')
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean)
  if (lines.length > 20) {
    return { ok: false, error: '忙碌选择器最多 20 个' }
  }
  for (const line of lines) {
    if (line.length > 200) {
      return { ok: false, error: '单个忙碌选择器长度不能超过 200 字符' }
    }
    const openParen = (line.match(/\(/g) || []).length
    const closeParen = (line.match(/\)/g) || []).length
    const openBracket = (line.match(/\[/g) || []).length
    const closeBracket = (line.match(/\]/g) || []).length
    if (openParen !== closeParen || openBracket !== closeBracket) {
      return { ok: false, error: `忙碌选择器括号不匹配：${line}` }
    }
    const singleQuotes = (line.match(/'/g) || []).length
    const doubleQuotes = (line.match(/"/g) || []).length
    if (singleQuotes % 2 !== 0 || doubleQuotes % 2 !== 0) {
      return { ok: false, error: `忙碌选择器引号不匹配：${line}` }
    }
  }
  if (lines.length) {
    gv[UI_BUSY_SELECTORS_KEY] = lines
  } else {
    delete gv[UI_BUSY_SELECTORS_KEY]
  }

  const ready = String(readySelector || '').trim()
  if (ready.length > 300) {
    return { ok: false, error: '就绪选择器长度不能超过 300 字符' }
  }
  if (ready) {
    if (/[\u4e00-\u9fff]/.test(ready)) {
      return {
        ok: false,
        error: '就绪选择器只能填一个 CSS（如 .main-content），不要写中文「或」连接多个',
      }
    }
    if (/\s+or\s+/i.test(ready) || /\|\|/.test(ready)) {
      return {
        ok: false,
        error: '就绪选择器只支持单个 CSS，不要用 or / || 连接多个',
      }
    }
    const openParen = (ready.match(/\(/g) || []).length
    const closeParen = (ready.match(/\)/g) || []).length
    const openBracket = (ready.match(/\[/g) || []).length
    const closeBracket = (ready.match(/\]/g) || []).length
    if (openParen !== closeParen || openBracket !== closeBracket) {
      return { ok: false, error: `就绪选择器括号不匹配：${ready}` }
    }
    const singleQuotes = (ready.match(/'/g) || []).length
    const doubleQuotes = (ready.match(/"/g) || []).length
    if (singleQuotes % 2 !== 0 || doubleQuotes % 2 !== 0) {
      return { ok: false, error: `就绪选择器引号不匹配：${ready}` }
    }
    gv[UI_READY_SELECTOR_KEY] = ready
  } else {
    delete gv[UI_READY_SELECTOR_KEY]
  }

  let retry = Number(readinessRetry)
  if (!Number.isFinite(retry)) retry = DEFAULT_UI_READINESS_RETRY
  retry = Math.trunc(retry)
  if (retry < 0 || retry > 3) {
    return { ok: false, error: '就绪重试次数须在 0–3 之间' }
  }
  if (retry === DEFAULT_UI_READINESS_RETRY) {
    delete gv[UI_READINESS_RETRY_KEY]
  } else {
    gv[UI_READINESS_RETRY_KEY] = retry
  }

  let probe = Number(busyAppearProbeMs)
  if (!Number.isFinite(probe)) probe = DEFAULT_UI_BUSY_APPEAR_PROBE_MS
  probe = Math.trunc(probe)
  if (probe < 0 || probe > 5000) {
    return { ok: false, error: '忙碌遮罩探测窗口须在 0–5000ms 之间' }
  }
  if (probe === DEFAULT_UI_BUSY_APPEAR_PROBE_MS) {
    delete gv[UI_BUSY_APPEAR_PROBE_MS_KEY]
  } else {
    gv[UI_BUSY_APPEAR_PROBE_MS_KEY] = probe
  }

  let settle = Number(actionSettleMs)
  if (!Number.isFinite(settle)) settle = DEFAULT_UI_ACTION_SETTLE_MS
  settle = Math.trunc(settle)
  if (settle < 0 || settle > 30000) {
    return { ok: false, error: '操作后页面沉降预算须在 0–30000ms 之间' }
  }
  if (settle === DEFAULT_UI_ACTION_SETTLE_MS) {
    delete gv[UI_ACTION_SETTLE_MS_KEY]
  } else {
    gv[UI_ACTION_SETTLE_MS_KEY] = settle
  }

  let quiet = Number(actionSettleQuietMs)
  if (!Number.isFinite(quiet)) quiet = DEFAULT_UI_ACTION_SETTLE_QUIET_MS
  quiet = Math.trunc(quiet)
  if (quiet < 0 || quiet > 5000) {
    return { ok: false, error: '操作后 DOM 静默窗口须在 0–5000ms 之间' }
  }
  if (quiet === DEFAULT_UI_ACTION_SETTLE_QUIET_MS) {
    delete gv[UI_ACTION_SETTLE_QUIET_MS_KEY]
  } else {
    gv[UI_ACTION_SETTLE_QUIET_MS_KEY] = quiet
  }

  return { ok: true, globalVars: gv }
}

/**
 * 从环境 global_vars 读取启动登录态表单状态
 */
export function getEnvUiAuthInjectForm(globalVars) {
  const gv = globalVars && typeof globalVars === 'object' ? globalVars : {}
  const raw = gv[UI_AUTH_INJECT_KEY]
  const inject = raw && typeof raw === 'object' && !Array.isArray(raw) ? raw : null
  const storageRaw = gv[UI_STORAGE_STATE_KEY]
  let storageStateText = ''
  let legacyStorageDoc = null
  let legacyPath = ''
  if (storageRaw != null && storageRaw !== '') {
    if (typeof storageRaw === 'object') {
      legacyStorageDoc = storageRaw
      try {
        storageStateText = JSON.stringify(storageRaw, null, 2)
      } catch {
        storageStateText = ''
      }
    } else {
      legacyPath = String(storageRaw).trim()
      storageStateText = legacyPath
    }
  }

  let profiles = []
  const profilesRaw = gv[UI_AUTH_PROFILES_KEY]
  if (Array.isArray(profilesRaw)) {
    profiles = profilesRaw.map((p, idx) => ({
      id: String(p?.id || `p-${idx}`),
      name: String(p?.name || `站点${idx + 1}`),
      enabled: p?.enabled !== false,
      host_hint: String(p?.host_hint || p?.match_host || ''),
      note: String(p?.note || ''),
      storage_state:
        p?.storage_state && typeof p.storage_state === 'object'
          ? p.storage_state
          : { cookies: [], origins: [] },
    }))
  }

  // 兼容：旧版单份 storage_state 对象升迁为一条「默认」配置展示
  if (!profiles.length && legacyStorageDoc && typeof legacyStorageDoc === 'object') {
    profiles = [
      {
        id: 'legacy-default',
        name: '默认登录态',
        enabled: true,
        host_hint: '',
        note: '由旧版 storage_state 自动迁移，可改名',
        storage_state: legacyStorageDoc,
      },
    ]
  }

  const headers = inject?.headers && typeof inject.headers === 'object' ? inject.headers : {}
  const authHeader = String(headers.Authorization || headers.authorization || '')
  const localStorage = Array.isArray(inject?.local_storage)
    ? inject.local_storage.map((r) => ({
        key: String(r?.key || ''),
        value: String(r?.value ?? ''),
      }))
    : []
  const sessionStorage = Array.isArray(inject?.session_storage)
    ? inject.session_storage.map((r) => ({
        key: String(r?.key || ''),
        value: String(r?.value ?? ''),
      }))
    : []
  const cookies = Array.isArray(inject?.cookies)
    ? inject.cookies.map((r) => ({
        name: String(r?.name || ''),
        value: String(r?.value ?? ''),
        domain: String(r?.domain || ''),
        path: String(r?.path || '/'),
        url: String(r?.url || ''),
      }))
    : []
  const hasConfig = Boolean(
    authHeader
    || localStorage.some((r) => r.key)
    || sessionStorage.some((r) => r.key)
    || cookies.some((r) => r.name)
    || profiles.length
    || legacyPath
  )

  const flagRaw = gv[UI_AUTH_ENABLED_KEY]
  let enabled
  if (flagRaw === false || flagRaw === 0 || flagRaw === 'false' || flagRaw === '0') {
    enabled = false
  } else if (flagRaw === true || flagRaw === 1 || flagRaw === 'true' || flagRaw === '1') {
    enabled = true
  } else {
    // 兼容旧数据：有配置即视为启用
    enabled = hasConfig
  }

  return {
    enabled,
    hasConfig,
    authorization: authHeader,
    localStorage: localStorage.length ? localStorage : [{ key: '', value: '' }],
    sessionStorage: sessionStorage.length ? sessionStorage : [{ key: '', value: '' }],
    cookies: cookies.length ? cookies : [{ name: '', value: '', domain: '', path: '/', url: '' }],
    storageStateText,
    legacyPath,
    profiles,
  }
}

/**
 * 当前环境是否已配置且总开关开启（运行弹窗提示用）
 */
export function envHasUiAuthInject(globalVars) {
  const form = getEnvUiAuthInjectForm(globalVars)
  return Boolean(form.enabled && form.hasConfig)
}

/**
 * 合并启动登录态注入到 global_vars
 * @returns {{ ok: true, globalVars: object } | { ok: false, error: string }}
 */
export function mergeEnvUiAuthInject(
  globalVars,
  {
    enabled = false,
    authorization = '',
    localStorage = [],
    sessionStorage = [],
    cookies = [],
    storageStateText = '',
    profiles = [],
    legacyPath = '',
  } = {}
) {
  const gv = globalVars && typeof globalVars === 'object' ? { ...globalVars } : {}
  delete gv[UI_AUTH_INJECT_KEY]
  delete gv[UI_STORAGE_STATE_KEY]
  delete gv[UI_AUTH_PROFILES_KEY]
  delete gv[UI_AUTH_ENABLED_KEY]

  // 停用时仍写回配置（不清数据），仅用 __ui_auth_enabled=false 控制下发
  const headers = {}
  const auth = String(authorization || '').trim()
  if (auth) {
    headers.Authorization = auth
  }

  const ls = []
  for (const row of localStorage || []) {
    const key = String(row?.key || '').trim()
    if (!key) continue
    if (key.length > 200) {
      return { ok: false, error: 'LocalStorage 键名过长' }
    }
    ls.push({ key, value: String(row?.value ?? '') })
  }

  const ss = []
  for (const row of sessionStorage || []) {
    const key = String(row?.key || '').trim()
    if (!key) continue
    if (key.length > 200) {
      return { ok: false, error: 'SessionStorage 键名过长' }
    }
    ss.push({ key, value: String(row?.value ?? '') })
  }

  const ck = []
  for (const row of cookies || []) {
    const name = String(row?.name || '').trim()
    if (!name) continue
    const domain = String(row?.domain || '').trim()
    const url = String(row?.url || '').trim()
    const path = String(row?.path || '/').trim() || '/'
    if (!domain && !url) {
      return { ok: false, error: `Cookie「${name}」须填写 domain 或 url` }
    }
    const item = {
      name,
      value: String(row?.value ?? ''),
      path,
    }
    if (domain) item.domain = domain
    if (url) item.url = url
    ck.push(item)
  }

  if (Object.keys(headers).length || ls.length || ss.length || ck.length) {
    gv[UI_AUTH_INJECT_KEY] = {
      headers,
      local_storage: ls,
      session_storage: ss,
      cookies: ck,
    }
  }

  const profileList = []
  for (const p of profiles || []) {
    const name = String(p?.name || '').trim() || '未命名'
    if (name.length > 80) {
      return { ok: false, error: '登录态名称过长' }
    }
    const state = p?.storage_state
    if (!state || typeof state !== 'object') {
      return { ok: false, error: `登录态「${name}」缺少 storage_state` }
    }
    if (
      !('cookies' in state)
      && !('origins' in state)
      && !('sessionStorageOrigins' in state)
    ) {
      return { ok: false, error: `登录态「${name}」须包含 cookies / origins / sessionStorageOrigins` }
    }
    const entry = {
      name,
      enabled: p?.enabled !== false,
      storage_state: state,
    }
    const hostHint = String(p?.host_hint || '').trim()
    if (hostHint) entry.host_hint = hostHint
    const note = String(p?.note || '').trim()
    if (note) entry.note = note
    profileList.push(entry)
  }
  if (profileList.length) {
    gv[UI_AUTH_PROFILES_KEY] = profileList
  }

  // 兼容：无 profiles 时仍可保存旧路径 / 粘贴 JSON
  if (!profileList.length) {
    const pathOnly = String(legacyPath || '').trim()
    const stateText = String(storageStateText || '').trim()
    if (pathOnly && !pathOnly.startsWith('{')) {
      if (/\r|\n/.test(pathOnly)) {
        return { ok: false, error: 'storage_state 路径不能包含换行' }
      }
      gv[UI_STORAGE_STATE_KEY] = pathOnly
    } else if (stateText) {
      if (stateText.startsWith('{')) {
        try {
          const parsed = JSON.parse(stateText)
          if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
            return { ok: false, error: 'storage_state JSON 须为对象' }
          }
          if (
            !('cookies' in parsed)
            && !('origins' in parsed)
            && !('sessionStorageOrigins' in parsed)
          ) {
            return { ok: false, error: 'storage_state 须包含 cookies、origins 或 sessionStorageOrigins' }
          }
          gv[UI_STORAGE_STATE_KEY] = parsed
        } catch {
          return { ok: false, error: 'storage_state JSON 无效' }
        }
      } else {
        if (/\r|\n/.test(stateText)) {
          return { ok: false, error: 'storage_state 路径不能包含换行' }
        }
        gv[UI_STORAGE_STATE_KEY] = stateText
      }
    }
  }

  const hasAny =
    Boolean(gv[UI_AUTH_INJECT_KEY])
    || Boolean(gv[UI_AUTH_PROFILES_KEY])
    || Boolean(gv[UI_STORAGE_STATE_KEY])

  // 有配置时始终写入总开关；无配置则不留空键
  if (hasAny) {
    gv[UI_AUTH_ENABLED_KEY] = Boolean(enabled)
  }

  return { ok: true, globalVars: gv }
}

/** 兼容录制 apply 事件：旧版仅 steps 数组，新版 { steps, description, applyMode, insertAtIndex } */
export function normalizeRecorderApplyPayload(payload) {
  if (Array.isArray(payload)) {
    return { steps: payload, description: '', applyMode: 'replace', insertAtIndex: null }
  }
  return {
    steps: Array.isArray(payload?.steps) ? payload.steps : [],
    description: (payload?.description || '').trim(),
    applyMode: payload?.applyMode || 'replace',
    insertAtIndex: payload?.insertAtIndex ?? null,
  }
}

