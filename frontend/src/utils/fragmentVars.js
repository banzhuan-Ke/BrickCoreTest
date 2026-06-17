/** 从片段步骤 JSON 中提取 ${{fragment.xxx}} 占位变量名 */
const FRAGMENT_VAR_PATTERN = /\$\{\{fragment\.([^}]+)\}\}/g

export function extractFragmentVarNames(steps) {
  const names = new Set()

  function scan(obj) {
    if (obj == null) return
    if (typeof obj === 'string') {
      FRAGMENT_VAR_PATTERN.lastIndex = 0
      let match
      while ((match = FRAGMENT_VAR_PATTERN.exec(obj)) !== null) {
        const key = (match[1] || '').trim()
        if (key) names.add(key)
      }
      return
    }
    if (Array.isArray(obj)) {
      obj.forEach(scan)
      return
    }
    if (typeof obj === 'object') {
      Object.values(obj).forEach(scan)
    }
  }

  scan(steps)
  return [...names].sort()
}

export function normalizeFragmentVariables(rawVars, placeholderNames = []) {
  const out = {}
  const source = rawVars && typeof rawVars === 'object' ? rawVars : {}
  for (const name of placeholderNames) {
    out[name] = source[name] ?? ''
  }
  for (const [key, val] of Object.entries(source)) {
    if (!(key in out)) out[key] = val ?? ''
  }
  return out
}
