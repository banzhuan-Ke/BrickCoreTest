/** 交互调试工具条快捷键：与 runner/tools/ui_debug_hotkeys.py 对齐 */

export const HOTKEY_ACTIONS = [
  'page_freeze',
  'pick',
  'highlight',
  'clear_highlight',
  'verify',
  'run_current',
  'run_selected',
  'run_to_end',
  'help',
  'close',
]

export const HOTKEY_ACTION_LABELS = {
  page_freeze: '冻结/解冻页面',
  pick: '拾取开关',
  highlight: '高亮',
  clear_highlight: '取消高亮',
  verify: '验证',
  run_current: '执行本步',
  run_selected: '执行勾选',
  run_to_end: '执行至末尾',
  help: '快捷键说明',
  close: '关闭浏览器',
}

export const DEFAULT_HOTKEYS = {
  page_freeze: 'Ctrl+Shift+F',
  pick: 'Ctrl+Shift+P',
  highlight: 'Ctrl+Shift+H',
  clear_highlight: 'Ctrl+Shift+G',
  verify: 'Ctrl+Shift+V',
  run_current: 'Ctrl+Shift+Enter',
  run_selected: 'Ctrl+Shift+S',
  run_to_end: 'Ctrl+Shift+E',
  help: 'F1',
  close: '',
}

const MOD_ORDER = ['Ctrl', 'Alt', 'Shift', 'Meta']

function normToken(token) {
  const t = String(token || '').trim()
  if (!t) return ''
  const low = t.toLowerCase()
  if (['ctrl', 'control', 'cmdorctrl'].includes(low)) return 'Ctrl'
  if (['alt', 'option'].includes(low)) return 'Alt'
  if (low === 'shift') return 'Shift'
  if (['meta', 'cmd', 'command', 'win', 'windows'].includes(low)) return 'Meta'
  if ([' ', 'space', 'spacebar'].includes(low)) return 'Space'
  if (['esc', 'escape'].includes(low)) return 'Escape'
  if (['return', 'enter'].includes(low)) return 'Enter'
  if (/^f\d{1,2}$/i.test(t)) return t.toUpperCase()
  if (t.length === 1) return /[a-z]/i.test(t) ? t.toUpperCase() : t
  return t
}

export function normalizeHotkeyCombo(raw) {
  const text = String(raw || '').trim()
  if (!text) return ''
  const parts = text.replace(/-/g, '+').split(/[+\s]+/).filter(Boolean)
  const mods = []
  let key = ''
  for (const p of parts) {
    const n = normToken(p)
    if (!n) continue
    if (MOD_ORDER.includes(n)) {
      if (!mods.includes(n)) mods.push(n)
    } else {
      key = n
    }
  }
  if (!key || MOD_ORDER.includes(key)) return ''
  if (key.length === 1 && /[A-Z0-9]/i.test(key) && !mods.length) return ''
  const modsSorted = MOD_ORDER.filter((m) => mods.includes(m))
  return [...modsSorted, key].join('+')
}

export function formatHotkeyLabel(combo) {
  return normalizeHotkeyCombo(combo) || '未绑定'
}

export function validateHotkeysMap(raw) {
  const out = Object.fromEntries(HOTKEY_ACTIONS.map((k) => [k, '']))
  if (!raw || typeof raw !== 'object') return out
  const used = {}
  for (const action of HOTKEY_ACTIONS) {
    if (!(action in raw)) continue
    const combo = normalizeHotkeyCombo(raw[action])
    if (!combo) {
      out[action] = ''
      continue
    }
    if (used[combo] && used[combo] !== action) {
      out[action] = ''
      continue
    }
    out[action] = combo
    used[combo] = action
  }
  return out
}

export function mergeHotkeys(...layers) {
  let merged = { ...DEFAULT_HOTKEYS }
  for (const layer of layers) {
    if (!layer || typeof layer !== 'object') continue
    const validated = validateHotkeysMap(layer)
    for (const action of HOTKEY_ACTIONS) {
      if (action in layer) merged[action] = validated[action]
      else if (validated[action]) merged[action] = validated[action]
    }
  }
  return validateHotkeysMap(merged)
}

export function storageKey(userId) {
  return `ui_debug_hotkeys:v1:${userId || 'anon'}`
}

export function loadStoredHotkeys(userId) {
  try {
    const raw = localStorage.getItem(storageKey(userId))
    if (!raw) return { ...DEFAULT_HOTKEYS }
    return mergeHotkeys(DEFAULT_HOTKEYS, JSON.parse(raw))
  } catch {
    return { ...DEFAULT_HOTKEYS }
  }
}

/**
 * 创建调试会话用：仅在用户曾于平台保存过快捷键时返回覆盖表。
 * 未保存过则返回 null，让 Runner 使用执行器 env（UI_DEBUG_HOTKEYS_JSON）+ 代码默认。
 */
export function getSessionHotkeyOverride(userId) {
  try {
    const raw = localStorage.getItem(storageKey(userId))
    if (!raw) return null
    return mergeHotkeys(DEFAULT_HOTKEYS, JSON.parse(raw))
  } catch {
    return null
  }
}

export function saveStoredHotkeys(userId, hotkeys) {
  const merged = mergeHotkeys(DEFAULT_HOTKEYS, hotkeys)
  localStorage.setItem(storageKey(userId), JSON.stringify(merged))
  return merged
}

/** 从 KeyboardEvent 生成 combo */
export function comboFromKeyboardEvent(e) {
  const mods = []
  if (e.ctrlKey) mods.push('Ctrl')
  if (e.altKey) mods.push('Alt')
  if (e.shiftKey) mods.push('Shift')
  if (e.metaKey) mods.push('Meta')
  let key = e.key || ''
  if (key === ' ') key = 'Space'
  if (key === 'Esc') key = 'Escape'
  if (/^f\d{1,2}$/i.test(key)) key = key.toUpperCase()
  else if (key.length === 1) key = key.toUpperCase()
  else if (key.startsWith('Arrow')) {
    /* keep */
  } else if (['Control', 'Alt', 'Shift', 'Meta'].includes(key)) {
    return ''
  }
  return normalizeHotkeyCombo([...mods, key].join('+'))
}
