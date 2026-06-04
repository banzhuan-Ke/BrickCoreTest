/**
 * 复制文本到剪贴板（兼容 HTTP 非安全上下文）
 */
function copyTextFallback(text) {
  const input = document.createElement('textarea')
  input.value = text ?? ''
  input.setAttribute('readonly', '')
  input.style.position = 'fixed'
  input.style.left = '-9999px'
  input.style.top = '0'
  document.body.appendChild(input)
  input.focus()
  input.select()
  const ok = document.execCommand('copy')
  document.body.removeChild(input)
  return ok
}

export async function copyToClipboard(text) {
  const value = text ?? ''
  if (navigator.clipboard?.writeText && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(value)
      return true
    } catch {
      // 降级到 execCommand
    }
  }
  return copyTextFallback(value)
}
