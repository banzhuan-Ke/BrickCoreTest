/** 内联数据工厂工具表达式：${{dt:md5|text=@token}} / ${{dt:md5|text='a|b'}} */

import { formatVarRef, insertVarRef } from './varInsert.js'

/**
 * 固定值优先用单引号（JSON Body 里外层通常是双引号，避免人手再改）。
 * 值内含单引号时回退双引号，并转义内部 " 与 \。
 * @param {string} val
 */
export function quoteDtLiteral(val) {
  const s = String(val ?? '')
  if (!s.includes("'")) {
    return `'${s.replace(/\\/g, '\\\\')}'`
  }
  const escaped = s.replace(/\\/g, '\\\\').replace(/"/g, '\\"')
  return `"${escaped}"`
}

/**
 * @param {string} toolId
 * @param {Record<string, string>} paramValues
 * @param {{ paramModes?: Record<string, 'literal'|'var'>, fieldTypes?: Record<string, string> }} [options]
 */
export function buildDtToolInner(toolId, paramValues = {}, options = {}) {
  const { paramModes = {}, fieldTypes = {} } = options
  let inner = `dt:${toolId}`
  for (const [key, val] of Object.entries(paramValues)) {
    if (val === '' || val == null) continue
    const raw = String(val)
    const mode = paramModes[key]
    const fieldType = fieldTypes[key]
    let encoded
    if (mode === 'var' || raw.startsWith('@')) {
      encoded = raw.startsWith('@') ? raw : `@${raw}`
    } else if (fieldType === 'number') {
      encoded = raw
    } else {
      encoded = quoteDtLiteral(raw)
    }
    inner += `|${key}=${encoded}`
  }
  return inner
}

export function formatDtToolRef(toolId, paramValues = {}, options = {}) {
  return formatVarRef(buildDtToolInner(toolId, paramValues, options))
}

export function insertDtToolRef(toolId, paramValues = {}, options = {}) {
  const inner = buildDtToolInner(toolId, paramValues, options)
  return insertVarRef(inner, options).then((result) => ({
    ...result,
    text: result?.text ?? formatDtToolRef(toolId, paramValues, options),
  }))
}
