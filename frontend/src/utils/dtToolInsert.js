/** 内联数据工厂工具表达式：${{dt:md5|text=@token}} / ${{dt:md5|text="a|b"}} */

import { formatVarRef, insertVarRef } from './varInsert.js'

/**
 * 固定值用双引号包裹（自动转义内部 " 和 \）
 * @param {string} val
 */
export function quoteDtLiteral(val) {
  const s = String(val ?? '')
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
  return insertVarRef(buildDtToolInner(toolId, paramValues, options))
}
