/** 环境/项目全局变量工具 */

const SECRET_KEY_PATTERN = /password|passwd|secret|token|api[_-]?key|authorization|credential|private/i

export function isSecretKey(key) {
  return SECRET_KEY_PATTERN.test(String(key || ''))
}

/** 是否为扩展存储格式 { value, description?, secret? } */
export function isVarEntryObject(value) {
  return value && typeof value === 'object' && !Array.isArray(value) && 'value' in value
}

/**
 * 系统保留键：存在 project/env.global_vars 里，但是模块配置对象，不是用例变量。
 * 出现在「项目共享变量」表格里会变成 [object Object]。
 */
const RESERVED_KEYS = new Set([
  'ai_settings',
  'zentao_export',
  'case_naming',
  'knowledge_settings',
  '__default_start_url',
  '__default_perf_worker_id',
  '__ui_timeout_scale',
  '__ui_nav_wait_until',
  '__ui_busy_selectors',
  '__ui_ready_selector',
  '__ui_readiness_retry',
  '__ui_busy_appear_probe_ms',
  '__ui_action_settle_ms',
  '__ui_action_settle_quiet_ms',
  '__ui_auth_inject',
  '__ui_storage_state',
  '__ui_auth_profiles',
  '__ui_auth_enabled',
])

export function isReservedGlobalVarKey(key) {
  const k = String(key || '').trim()
  if (!k) return false
  if (RESERVED_KEYS.has(k)) return true
  return k.startsWith('__')
}

/** 应隐藏的系统配置：保留键，或非 {value} 的嵌套对象 */
export function isSystemGlobalVarEntry(key, value) {
  if (isReservedGlobalVarKey(key)) return true
  if (value !== null && typeof value === 'object' && !Array.isArray(value) && !isVarEntryObject(value)) {
    return true
  }
  return false
}

export function pickSystemGlobalVars(globalVars) {
  const out = {}
  if (!globalVars || typeof globalVars !== 'object' || Array.isArray(globalVars)) return out
  for (const [key, value] of Object.entries(globalVars)) {
    if (isSystemGlobalVarEntry(key, value)) out[key] = value
  }
  return out
}

export function stripSystemGlobalVars(globalVars) {
  const out = {}
  if (!globalVars || typeof globalVars !== 'object' || Array.isArray(globalVars)) return out
  for (const [key, value] of Object.entries(globalVars)) {
    if (isSystemGlobalVarEntry(key, value)) continue
    out[key] = value
  }
  return out
}

/** 用户编辑结果 + 原系统配置；系统键始终以原配置为准 */
export function mergeUserVarsWithSystem(userVars, originalGlobalVars) {
  return {
    ...stripSystemGlobalVars(userVars),
    ...pickSystemGlobalVars(originalGlobalVars),
  }
}

export function parseVarEntry(key, value) {
  if (isSystemGlobalVarEntry(key, value)) {
    return {
      key: String(key),
      value,
      description: '',
      secret: false,
      _rawObject: true,
    }
  }
  if (isVarEntryObject(value)) {
    const rawVal = value.value
    return {
      key: String(key),
      value:
        rawVal === null || rawVal === undefined
          ? ''
          : typeof rawVal === 'object'
            ? JSON.stringify(rawVal)
            : String(rawVal),
      description: String(value.description || ''),
      secret: Boolean(value.secret) || isSecretKey(key),
      _rawObject: false,
    }
  }
  return {
    key: String(key),
    value:
      value === null || value === undefined
        ? ''
        : typeof value === 'object'
          ? JSON.stringify(value)
          : String(value),
    description: '',
    secret: isSecretKey(key),
    _rawObject: false,
  }
}

export function varsObjectToList(globalVars) {
  if (!globalVars || typeof globalVars !== 'object' || Array.isArray(globalVars)) {
    return []
  }
  return Object.entries(globalVars).map(([key, value]) => parseVarEntry(key, value))
}

export function listToVarsObject(list) {
  const out = {}
  for (const row of list || []) {
    const key = (row.key || '').trim()
    if (!key) continue
    if (row._rawObject) {
      out[key] = row.value
      continue
    }
    const entry = {
      value: row.value ?? '',
      description: (row.description || '').trim(),
    }
    if (row.secret) entry.secret = true
    out[key] = entry
  }
  return out
}

export function getVarDescription(globalVars, key) {
  if (!globalVars || !key) return ''
  const entry = globalVars[key]
  if (isVarEntryObject(entry)) return String(entry.description || '').trim()
  return ''
}

export function getVarValue(globalVars, key) {
  if (!globalVars || !key) return ''
  const entry = globalVars[key]
  if (isVarEntryObject(entry)) return entry.value ?? ''
  return entry ?? ''
}

/** 执行/预览用：扁平化为 { 变量名: 值字符串 }，跳过系统配置 */
export function flattenGlobalVars(globalVars) {
  if (!globalVars || typeof globalVars !== 'object' || Array.isArray(globalVars)) {
    return {}
  }
  const out = {}
  for (const [key, value] of Object.entries(stripSystemGlobalVars(globalVars))) {
    const k = String(key).trim()
    if (!k) continue
    if (isVarEntryObject(value)) {
      out[k] = value.value === null || value.value === undefined ? '' : String(value.value)
    } else if (value !== null && typeof value !== 'object') {
      out[k] = String(value)
    }
  }
  return out
}

/**
 * @returns {{ ok: boolean, error?: string, duplicates?: string[] }}
 */
export function validateVarList(list) {
  const keys = []
  const duplicates = []
  for (const row of list || []) {
    const key = (row.key || '').trim()
    if (!key) continue
    if (isReservedGlobalVarKey(key)) {
      return { ok: false, error: `「${key}」为系统保留配置键，不能作为普通变量名` }
    }
    if (keys.includes(key)) {
      if (!duplicates.includes(key)) duplicates.push(key)
    } else {
      keys.push(key)
    }
  }
  if (duplicates.length) {
    return { ok: false, error: `变量名重复：${duplicates.join('、')}`, duplicates }
  }
  return { ok: true }
}

export function validateVarsObject(obj) {
  if (obj === null || obj === undefined) return { ok: true }
  if (typeof obj !== 'object' || Array.isArray(obj)) {
    return { ok: false, error: '环境变量必须是 JSON 对象（键值对）' }
  }
  for (const [key, value] of Object.entries(obj)) {
    if (isSystemGlobalVarEntry(key, value)) continue
    if (isVarEntryObject(value)) {
      if (value.value !== null && typeof value.value === 'object') {
        return { ok: false, error: `变量「${key}」的值不能是嵌套对象或数组` }
      }
      continue
    }
    if (value !== null && typeof value === 'object') {
      return { ok: false, error: `变量「${key}」需使用扩展格式或字符串值` }
    }
  }
  return validateVarList(varsObjectToList(stripSystemGlobalVars(obj)))
}

export function formatVarsPreview(globalVars, maxKeys = 4) {
  const rows = userVarRows(globalVars)
  if (!rows.length) return '（空）'
  const keys = rows.map((r) => r.key)
  const shown = keys.slice(0, maxKeys).join(', ')
  const more = keys.length > maxKeys ? ` 等 ${keys.length} 项` : `（共 ${keys.length} 项）`
  return keys.length <= maxKeys ? `${shown}（${keys.length} 项）` : `${shown}${more}`
}

/** 用户可见的环境变量行（排除系统配置） */
export function userVarRows(globalVars) {
  return varsObjectToList(stripSystemGlobalVars(globalVars)).filter((r) => !r._rawObject)
}

export function countUserVars(globalVars) {
  return userVarRows(globalVars).length
}

export const BUILTIN_VAR_HINTS = [
  { key: 'random_int', label: '随机整数' },
  { key: 'random_name', label: '随机姓名' },
  { key: 'random_phone', label: '随机手机' },
  { key: 'random_email', label: '随机邮箱' },
  { key: 'today', label: '今天日期' },
  { key: 'now_time', label: '当前时间' },
]
