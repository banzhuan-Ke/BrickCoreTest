/** 从 axios 响应或 reject 对象提取后端 detail 文案 */
export function getApiErrorMessage(err, fallback = '操作失败') {
  const detail = err?.response?.data?.detail ?? err?.data?.detail
  if (typeof detail === 'string' && detail.trim()) {
    return detail.trim()
  }
  if (Array.isArray(detail) && detail.length) {
    const first = detail[0]
    if (typeof first === 'string') return first
    if (first?.msg) return String(first.msg)
  }
  return fallback
}

export function isDuplicateElementNameError(err) {
  const msg = getApiErrorMessage(err, '')
  return /元素名.*已存在/.test(msg)
}
