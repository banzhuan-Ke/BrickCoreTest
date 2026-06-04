/**
 * 格式化 JSON 文本
 * @param {string} text
 * @param {number} indent
 * @returns {{ ok: true, text: string } | { ok: false, error: string }}
 */
export function formatJsonText(text, indent = 2) {
  const trimmed = (text ?? '').trim()
  if (!trimmed) {
    return { ok: true, text: '' }
  }
  try {
    const parsed = JSON.parse(trimmed)
    return { ok: true, text: JSON.stringify(parsed, null, indent) }
  } catch (e) {
    return { ok: false, error: `JSON 格式错误：${e.message || '无法解析'}` }
  }
}

/** 压缩 JSON 为单行 */
export function compactJsonText(text) {
  const result = formatJsonText(text, 0)
  if (!result.ok) return result
  if (!result.text) return result
  try {
    return { ok: true, text: JSON.stringify(JSON.parse(result.text)) }
  } catch (e) {
    return { ok: false, error: e.message || '无法压缩' }
  }
}

/** 判断 body 类型是否适合 JSON 格式化 */
export function isJsonBodyType(bodyType) {
  return bodyType === 'json' || !bodyType
}
