/** 变量引用插入工具 */

let lastFocusedInput = null

if (typeof document !== 'undefined') {
  document.addEventListener(
    'focusin',
    (e) => {
      const t = e.target
      if (
        t instanceof HTMLInputElement ||
        t instanceof HTMLTextAreaElement ||
        (t?.isContentEditable && t.getAttribute('contenteditable') !== 'false')
      ) {
        lastFocusedInput = t
      }
    },
    true
  )
}

export function formatVarRef(name) {
  return `\${{${name}}}`
}

export function insertVarRef(name) {
  const text = formatVarRef(name)
  const el = lastFocusedInput
  if (el && (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement)) {
    const start = el.selectionStart ?? el.value.length
    const end = el.selectionEnd ?? start
    const val = el.value ?? ''
    el.value = val.slice(0, start) + text + val.slice(end)
    el.dispatchEvent(new Event('input', { bubbles: true }))
    const pos = start + text.length
    el.setSelectionRange(pos, pos)
    el.focus()
    return { ok: true, mode: 'insert' }
  }
  if (navigator.clipboard?.writeText) {
    return navigator.clipboard.writeText(text).then(() => ({ ok: true, mode: 'copy' }))
  }
  return Promise.resolve({ ok: false, mode: 'none' })
}
