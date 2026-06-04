/** 断言结果展示：长文本摘要、展开查看 */

export const ASSERTION_ACTUAL_PREVIEW_LEN = 80

const LONG_BODY_TYPES = new Set(['contains', 'not_contains', 'regex'])

export function assertionActualToText(val) {
  if (val === null || val === undefined) return ''
  if (typeof val === 'object') {
    try {
      return JSON.stringify(val, null, 2)
    } catch {
      return String(val)
    }
  }
  return String(val)
}

export function getAssertionActualLength(val) {
  return assertionActualToText(val).length
}

export function isLongAssertionActual(val, type) {
  const text = assertionActualToText(val)
  if (!text) return false
  if (LONG_BODY_TYPES.has(type)) return text.length > ASSERTION_ACTUAL_PREVIEW_LEN
  return text.length > ASSERTION_ACTUAL_PREVIEW_LEN || text.includes('\n')
}

export function getAssertionActualPreview(val, maxLen = ASSERTION_ACTUAL_PREVIEW_LEN) {
  const text = assertionActualToText(val)
  if (!text) return '-'
  const oneLine = text.replace(/\s+/g, ' ').trim()
  if (oneLine.length <= maxLen) return oneLine
  return `${oneLine.slice(0, maxLen)}…`
}

/** contains 失败时生成简短说明 */
export function getContainsFailHint(row) {
  const expected = row?.expected != null ? String(row.expected) : ''
  const len = getAssertionActualLength(row?.actual)
  if (!expected) {
    return len > 0 ? `响应约 ${formatByteSize(len)}，未匹配` : '响应为空'
  }
  const preview = expected.length > 24 ? `${expected.slice(0, 24)}…` : expected
  return `未包含「${preview}」· 响应约 ${formatByteSize(len)}`
}

export function formatByteSize(charLen) {
  if (charLen < 1024) return `${charLen} 字符`
  if (charLen < 1024 * 1024) return `${(charLen / 1024).toFixed(1)} KB`
  return `${(charLen / (1024 * 1024)).toFixed(2)} MB`
}

/** 在全文里定位 expected 首次出现（成功或辅助查看） */
export function findExpectedIndex(actualText, expected) {
  if (!expected || !actualText) return -1
  const term = String(expected)
  const idx = actualText.indexOf(term)
  if (idx >= 0) return idx
  return actualText.toLowerCase().indexOf(term.toLowerCase())
}

export function escapeHtml(text) {
  return String(text ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

/** 在文本中高亮 search（大小写不敏感），返回 HTML 字符串 */
export function buildHighlightedHtml(text, search) {
  const src = text ?? ''
  const term = String(search ?? '')
  if (!term) return escapeHtml(src)

  const lower = src.toLowerCase()
  const lowerTerm = term.toLowerCase()
  let result = ''
  let i = 0

  while (i < src.length) {
    const idx = lower.indexOf(lowerTerm, i)
    if (idx === -1) {
      result += escapeHtml(src.slice(i))
      break
    }
    result += escapeHtml(src.slice(i, idx))
    result += `<mark class="copyable-pre__highlight">${escapeHtml(src.slice(idx, idx + term.length))}</mark>`
    i = idx + term.length
  }
  return result
}

export function countHighlightMatches(text, search) {
  const src = text ?? ''
  const term = String(search ?? '')
  if (!term) return 0
  const lower = src.toLowerCase()
  const lowerTerm = term.toLowerCase()
  let count = 0
  let i = 0
  while (i < lower.length) {
    const idx = lower.indexOf(lowerTerm, i)
    if (idx === -1) break
    count += 1
    i = idx + lowerTerm.length
  }
  return count
}
