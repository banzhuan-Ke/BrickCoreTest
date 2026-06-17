/** 环境/项目全局变量工具 */

const SECRET_KEY_PATTERN = /password|passwd|secret|token|api[_-]?key|authorization|credential|private/i

export function isSecretKey(key) {
  return SECRET_KEY_PATTERN.test(String(key || ''))
}

/** 是否为扩展存储格式 { value, description?, secret? } */
export function isVarEntryObject(value) {
  return value && typeof value === 'object' && !Array.isArray(value) && 'value' in value
}

/** 系统保留键（项目 global_vars 内嵌套配置，非表格变量） */
const RESERVED_KEYS = new Set(['ai_settings', 'zentao_export'])

export function parseVarEntry(key, value) {
  if (RESERVED_KEYS.has(key) && typeof value === 'object' && value !== null && !isVarEntryObject(value)) {
    return {
      key: String(key),
      value,
      description: '',
      secret: false,
      _rawObject: true,
    }
  }
  if (isVarEntryObject(value)) {
    return {
      key: String(key),
      value:
        value.value === null || value.value === undefined
          ? ''
          : typeof value.value === 'object'
            ? value.value
            : String(value.value),
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
          ? value
          : String(value),
    description: '',
    secret: isSecretKey(key),
    _rawObject: typeof value === 'object' && value !== null,
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

/**
 * @returns {{ ok: boolean, error?: string, duplicates?: string[] }}
 */
export function validateVarList(list) {
  const keys = []
  const duplicates = []
  for (const row of list || []) {
    const key = (row.key || '').trim()
    if (!key) continue
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
    if (RESERVED_KEYS.has(key)) continue
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
  return validateVarList(varsObjectToList(obj))
}

export function formatVarsPreview(globalVars, maxKeys = 4) {
  const rows = varsObjectToList(globalVars).filter((r) => !r._rawObject)
  if (!rows.length) return '（空）'
  const keys = rows.map((r) => r.key)
  const shown = keys.slice(0, maxKeys).join(', ')
  const more = keys.length > maxKeys ? ` 等 ${keys.length} 项` : `（共 ${keys.length} 项）`
  return keys.length <= maxKeys ? `${shown}（${keys.length} 项）` : `${shown}${more}`
}

export const BUILTIN_VAR_HINTS = [
  { key: 'random_int', label: '随机整数' },
  { key: 'random_name', label: '随机姓名' },
  { key: 'random_phone', label: '随机手机' },
  { key: 'random_email', label: '随机邮箱' },
  { key: 'today', label: '今天日期' },
  { key: 'now_time', label: '当前时间' },
]
