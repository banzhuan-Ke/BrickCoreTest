/** 环境/项目全局变量工具 */

const SECRET_KEY_PATTERN = /password|passwd|secret|token|api[_-]?key|authorization|credential|private/i

export function isSecretKey(key) {
  return SECRET_KEY_PATTERN.test(String(key || ''))
}

export function varsObjectToList(globalVars) {
  if (!globalVars || typeof globalVars !== 'object' || Array.isArray(globalVars)) {
    return []
  }
  return Object.entries(globalVars).map(([key, value]) => ({
    key: String(key),
    value: value === null || value === undefined ? '' : String(value),
    secret: isSecretKey(key),
  }))
}

export function listToVarsObject(list) {
  const out = {}
  for (const row of list || []) {
    const key = (row.key || '').trim()
    if (!key) continue
    out[key] = row.value ?? ''
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
  return validateVarList(varsObjectToList(obj))
}

export function formatVarsPreview(globalVars, maxKeys = 4) {
  if (!globalVars || typeof globalVars !== 'object' || Array.isArray(globalVars)) {
    return '—'
  }
  const keys = Object.keys(globalVars)
  if (!keys.length) return '（空）'
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
