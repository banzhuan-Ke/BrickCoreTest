export const BASIC_ENV_FIELDS = [
  { key: 'env_name', label: '环境名称' },
  { key: 'browser', label: '浏览器' },
  { key: 'headless', label: '无头模式' },
  { key: 'device_id', label: '设备 ID' },
  { key: 'target_host', label: '目标地址' }
]

const RESERVED_KEYS = new Set(['variables', 'case_naming', ...BASIC_ENV_FIELDS.map((f) => f.key)])

const SENSITIVE_KEY_RE = /password|token|secret|api[_-]?key|auth|credential|private|passwd/i
const DYNAMIC_VALUE_RE = /Faker\.|\$\{|\$\(/i

export function isSensitiveEnvKey(key) {
  return SENSITIVE_KEY_RE.test(String(key || ''))
}

export function isDynamicEnvValue(value) {
  return DYNAMIC_VALUE_RE.test(String(value ?? ''))
}

export function maskSensitiveValue(value, visibleTail = 4) {
  const text = String(value ?? '')
  if (!text) return '—'
  if (text.length <= visibleTail) return '••••'
  return `${'•'.repeat(Math.min(12, text.length - visibleTail))}${text.slice(-visibleTail)}`
}

export function buildBasicEnvItems(env, fields = BASIC_ENV_FIELDS) {
  if (!env || typeof env !== 'object') return []
  return fields
    .filter((field) => env[field.key] != null && env[field.key] !== '')
    .map((field) => ({
      key: field.key,
      label: field.label,
      value: env[field.key]
    }))
}

export function buildVariableRows(variables) {
  if (!variables || typeof variables !== 'object') return []
  return Object.entries(variables).map(([name, value]) => {
    const text = value == null ? '' : String(value)
    return {
      name,
      value: text,
      sensitive: isSensitiveEnvKey(name),
      dynamic: isDynamicEnvValue(text)
    }
  })
}

export function buildNamingItems(caseNaming) {
  if (!caseNaming || typeof caseNaming !== 'object') return []
  const templates = Array.isArray(caseNaming.templates) ? caseNaming.templates : []
  return templates.map((item) => ({
    name: item.name || item.id || '未命名模板',
    enabled: !!item.enabled,
    version: item.version
  }))
}

export function buildOtherEnvItems(env, fields = BASIC_ENV_FIELDS) {
  if (!env || typeof env !== 'object') return []
  const known = new Set([...RESERVED_KEYS, ...fields.map((f) => f.key)])
  return Object.entries(env)
    .filter(([key, value]) => !known.has(key) && value != null && value !== '')
    .map(([key, value]) => ({
      key,
      label: key,
      value: typeof value === 'object' ? JSON.stringify(value) : value
    }))
}
