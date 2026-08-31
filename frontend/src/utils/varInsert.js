/** 变量引用插入工具 */

import { wrapJsonStringValueIfNeeded } from './jsonInsertWrap.js'

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

/** 解析 ${{name}} 或裸 name */
export function parseVarRefString(refOrName) {
  const raw = String(refOrName ?? '').trim()
  const m = raw.match(/^\$\{\{(.+)\}\}$/)
  return m ? m[1] : raw
}

function applyInsertTransform(text, ctx, options = {}) {
  if (typeof options.transformText === 'function') {
    return options.transformText(text, ctx) || text
  }
  if (options.skipJsonWrap) return text
  return wrapJsonStringValueIfNeeded(text, ctx.before, ctx.after || '')
}

export function insertVarRef(name, options = {}) {
  let text = formatVarRef(name)
  const explicit = options.target
  const candidates = [explicit, insertTargetSnapshot, lastFocusedInput].filter(isValidInsertTarget)
  const el = candidates[0] || null

  if (el && (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement)) {
    const start = el.selectionStart ?? el.value.length
    const end = el.selectionEnd ?? start
    const val = el.value ?? ''
    const before = val.slice(0, start)
    const after = val.slice(end)
    text = applyInsertTransform(text, { before, after, el }, options)
    el.value = before + text + after
    el.dispatchEvent(new Event('input', { bubbles: true }))
    const pos = start + text.length
    el.setSelectionRange(pos, pos)
    el.focus()
    return Promise.resolve({ ok: true, mode: 'insert', text })
  }
  if (navigator.clipboard?.writeText) {
    return navigator.clipboard.writeText(text).then(() => ({ ok: true, mode: 'copy', text }))
  }
  return Promise.resolve({ ok: false, mode: 'none', text })
}

/** 从完整 ${{...}} 或裸 name 插入（变量 / df 标签 / 工具表达式 inner 均可用） */
export async function insertFullVarRef(refOrName, options = {}) {
  const name = parseVarRefString(refOrName)
  const result = await insertVarRef(name, options)
  return {
    ...result,
    display: result.text || formatVarRef(name),
  }
}
