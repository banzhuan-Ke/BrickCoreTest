/** 变量引用插入工具 */

/** 仅排除「插入 UI」自身，不能排除业务编辑弹窗（如 Web 步骤编辑也在 el-dialog 内） */
const INSERT_UI_SELECTOR =
  '.var-insert-popover, .tool-insert-popover, .var-insert-panel, .tool-insert-panel, .tool-insert-param-dialog, .df-tag-picker-dialog'

let lastFocusedInput = null
let insertTargetSnapshot = null

function isInsertExcluded(el) {
  if (!el || !(el instanceof Element)) return true
  return !!el.closest(INSERT_UI_SELECTOR)
}

function isValidInsertTarget(el) {
  return (
    el &&
    !isInsertExcluded(el) &&
    (el instanceof HTMLInputElement ||
      el instanceof HTMLTextAreaElement ||
      (el.isContentEditable && el.getAttribute('contenteditable') !== 'false'))
  )
}

if (typeof document !== 'undefined') {
  document.addEventListener(
    'focusin',
    (e) => {
      const t = e.target
      if (isValidInsertTarget(t)) {
        lastFocusedInput = t
      }
    },
    true
  )
}

/** 打开插入面板前调用，锁定当前编辑中的输入框 */
export function snapshotInsertTarget() {
  if (isValidInsertTarget(lastFocusedInput)) {
    insertTargetSnapshot = lastFocusedInput
  } else {
    insertTargetSnapshot = null
  }
}

export function clearInsertTargetSnapshot() {
  insertTargetSnapshot = null
}

export function formatVarRef(name) {
  return `\${{${name}}}`
}

export function insertVarRef(name, options = {}) {
  const text = formatVarRef(name)
  const explicit = options.target
  const candidates = [explicit, insertTargetSnapshot, lastFocusedInput].filter(isValidInsertTarget)
  const el = candidates[0] || null

  if (el && (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement)) {
    const start = el.selectionStart ?? el.value.length
    const end = el.selectionEnd ?? start
    const val = el.value ?? ''
    el.value = val.slice(0, start) + text + val.slice(end)
    el.dispatchEvent(new Event('input', { bubbles: true }))
    const pos = start + text.length
    el.setSelectionRange(pos, pos)
    el.focus()
    return Promise.resolve({ ok: true, mode: 'insert' })
  }
  if (navigator.clipboard?.writeText) {
    return navigator.clipboard.writeText(text).then(() => ({ ok: true, mode: 'copy' }))
  }
  return Promise.resolve({ ok: false, mode: 'none' })
}
