/** 在 JSON 文本编辑器中插入占位符时，自动补外层双引号 */

export function isInsideJsonDoubleString(before) {
  let quoteCount = 0
  for (let i = 0; i < before.length; i++) {
    if (before[i] === '\\') {
      i++
      continue
    }
    if (before[i] === '"') quoteCount++
  }
  return quoteCount % 2 === 1
}

/**
 * 光标是否处在 JSON 字符串值位置（对象键后 / 数组首项等），且尚未在双引号内。
 */
export function shouldWrapAsJsonStringValue(before, after = '') {
  if (isInsideJsonDoubleString(before)) return false
  if (/^\s*"/.test(after)) return false
  if (/:\s*$/.test(before)) return true
  if (/\[\s*$/.test(before)) return true
  return false
}

export function wrapJsonStringValueIfNeeded(text, before, after = '') {
  if (shouldWrapAsJsonStringValue(before, after)) {
    return `"${text}"`
  }
  return text
}
