/** 交互调试：定位器回填与步骤能力判断 */
import { buildStepFromKeyword } from '@/utils/stepHelper.js'

const LOCATOR_KEYS = ['locator', 'selector', 'start_selector', 'first_locator', 'second_locator']
const FRAME_KEYS = ['frame', 'iframe']

export function isFrameStep(step) {
  const method = String(step?.method || '')
  return method.startsWith('frame_')
}

function paramValue(params, key) {
  const val = params?.[key]
  return val != null && String(val).trim() !== '' ? String(val).trim() : ''
}

export function splitCombinedLocator(locator) {
  const raw = String(locator || '').trim()
  if (!raw.includes('||')) {
    return { frame: '', locator: raw }
  }
  const idx = raw.indexOf('||')
  return {
    frame: raw.slice(0, idx).trim(),
    locator: raw.slice(idx + 2).trim(),
  }
}

export function stepHasLocator(step) {
  if (!step || typeof step !== 'object') return false
  const params = step.params || {}
  if (isFrameStep(step)) {
    const hasFrame = FRAME_KEYS.some((key) => paramValue(params, key))
    const hasLocator = LOCATOR_KEYS.some((key) => paramValue(params, key))
    return hasFrame && hasLocator
  }
  return LOCATOR_KEYS.some((key) => paramValue(params, key))
}

export function pickResultKey(result) {
  if (!result || result.type !== 'pick') return ''
  if (result.pick_id) return String(result.pick_id)
  return `legacy:${result.locator || ''}`
}

/** 拾取结果是否更像可填控件（input / textarea / contenteditable） */
export function isFillablePickMeta(meta = {}) {
  const tag = String(meta.tag || '').toLowerCase()
  const inputType = String(meta.inputType || '').toLowerCase()
  const cls = String(meta.class || '').toLowerCase()
  const role = String(meta.role || '').toLowerCase()
  if (tag === 'textarea') return true
  if (role === 'textbox') return true
  if (cls.includes('el-input__inner') || cls.includes('el-textarea__inner')) return true
  if (tag === 'input') {
    return !['checkbox', 'radio', 'file', 'hidden', 'button', 'submit', 'reset', 'image'].includes(inputType)
  }
  if (inputType === 'text' || inputType === 'password' || inputType === 'number') return true
  return false
}

/** 定位器是否停在常见输入组件外壳（fill 易失败） */
export function isInputShellLocator(locator = '') {
  const raw = String(locator || '').trim()
  const core = raw.includes('||') ? raw.slice(raw.indexOf('||') + 2).trim() : raw
  if (!core) return false
  if (/input\.el-input__inner|textarea\.el-textarea__inner|(^|[\s>])input(\.|$|\s|\[)|(^|[\s>])textarea(\.|$|\s|\[)/i.test(core)) {
    return false
  }
  return /(^|[\s>])div\.(el-input|el-textarea|ant-input-affix-wrapper)(\.[a-zA-Z0-9_-]+)*$/i.test(core)
}

/** 候选列表展示短标签（语义 / 结构） */
export function formatPickCandidateLabel(candidate = '') {
  const c = String(candidate || '')
  if (c.startsWith('get_by_role=textbox') || c.startsWith('get_by_placeholder=')) {
    return `语义 · ${c}`
  }
  if (c.includes('input.el-input__inner') || c.includes('textarea.el-textarea__inner')) {
    return `可填 · ${c}`
  }
  if (isInputShellLocator(c)) {
    return `外壳 · ${c}`
  }
  return c
}

/** 根据拾取元素类型推荐步骤关键字模板 */
export function suggestPickStepTemplate(meta = {}, options = {}) {
  // 仅以实际回填的 frame 选择器为准；勿用 frameUrl 误判（iframe 内 pageUrl/frameUrl 常同值且未必已生成 iframe|| 前缀）
  const frame = String(options.frame || meta.frame || meta.pickedFrame || '').trim()
  const hasFrame = !!frame
  const tag = String(meta.tag || '').toLowerCase()
  const cls = String(meta.class || meta.role || '').toLowerCase()

  if (isFillablePickMeta(meta)) {
    if (hasFrame) {
      return {
        keyword: 'iframe内元素输入',
        method: 'frame_fill_value',
        params: { frame: '', locator: '', value: '', index: 1 },
      }
    }
    return {
      keyword: '元素输入',
      method: 'fill_value',
      params: { locator: '', value: '', timeout: 20000 },
    }
  }
  if (tag === 'select' || cls.includes('el-select') || cls.includes('ant-select')) {
    return {
      keyword: '点击元素',
      method: 'click_ele',
      params: {
        locator: '',
        index: 1,
        force: false,
        timeout: 20000,
        wait_download: false,
        save_path: '',
        var_name: '',
        download_timeout: 60000,
        accept_dialog: false,
        dismiss_dialog: false,
        dialog_timeout: 10000,
        prompt_text: '',
      },
    }
  }
  return {
    keyword: '点击元素',
    method: 'click_ele',
    params: {
      locator: '',
      index: 1,
      force: false,
      timeout: 20000,
      wait_download: false,
      save_path: '',
      var_name: '',
      download_timeout: 60000,
      accept_dialog: false,
      dismiss_dialog: false,
      dialog_timeout: 10000,
      prompt_text: '',
    },
  }
}

export function applyWebLocatorToStep(steps, stepIndex, payload) {
  const copy = JSON.parse(JSON.stringify(steps || []))
  const step = copy[stepIndex]
  if (!step) return { steps: copy, updated: false }

  const matchIndex = payload.match_index ?? payload.matchIndex ?? step.params?.index ?? 1
  const split = splitCombinedLocator(payload.locator)
  const frame = (payload.frame || split.frame || '').trim()
  const elementLocator = (payload.element_locator || split.locator || payload.locator || '').trim()
  const useFrame = isFrameStep(step) || !!frame
  const combinedForDisambig = useFrame
    ? `${frame ? frame + '||' : ''}${elementLocator}`
    : (payload.locator || elementLocator || '')
  // 定位已消歧时勿叠大 index（与后端 apply_index_from_meta 对齐）
  const locatorDisambiguated = (() => {
    const core = String(combinedForDisambig).split('||').pop() || ''
    const low = core.toLowerCase()
    if (/^#[A-Za-z_][\w:-]*$/.test(core.trim().split(/\s/)[0] || '')) return true
    if (core.startsWith('[data-testid=')) return true
    if (core.startsWith('get_by_placeholder=') || core.startsWith('get_by_label=')) return true
    if (core.startsWith('get_by_role=') && core.includes(',')) return true
    if (low.includes('nth-of-type(') || low.includes('nth-child(') || low.includes('>> nth=')) return true
    if (/\[(?:name|placeholder|aria-label|title)\s*=/i.test(core)) return true
    return false
  })()
  const resolvedIndex = locatorDisambiguated ? 1 : matchIndex

  const nextParams = {
    ...step.params,
    index: resolvedIndex,
  }

  if (useFrame) {
    nextParams.frame = frame
    nextParams.locator = elementLocator
  } else {
    nextParams.locator = payload.locator || elementLocator
    delete nextParams.frame
    delete nextParams.iframe
  }

  copy[stepIndex] = {
    ...step,
    params: nextParams,
    meta: {
      ...(step.meta || {}),
      ...(payload.meta || {}),
      candidates: payload.candidates || payload.meta?.candidates || step.meta?.candidates || [],
      matchIndex,
      pickedFrame: frame || undefined,
    },
  }
  return { steps: copy, updated: true }
}

/**
 * 将拾取结果写入已有步骤，或插入为新步骤
 * @returns {{ steps: Array, updated: boolean, stepIndex: number }}
 */
export function applyPickLocatorToSteps(steps, payload, options = {}) {
  const mode = options.mode || payload.mode || 'replace'
  const list = JSON.parse(JSON.stringify(steps || []))
  const targetIndex = Number(options.stepIndex ?? payload.stepIndex ?? 0)

  if (mode === 'insert') {
    const template = options.template || suggestPickStepTemplate(payload.meta || payload.element || {}, {
      frame: payload.frame || '',
    })
    const blank = buildStepFromKeyword(template)
    const nameHint = (payload.meta?.accessibleName || payload.meta?.text || payload.element?.text || '').trim()
    if (nameHint) {
      blank.desc = `${blank.keyword} - ${nameHint.slice(0, 24)}`
    }
    const insertAtRaw = Number(options.insertAt ?? payload.insertAt ?? targetIndex + 1)
    const insertAt = Math.max(0, Math.min(insertAtRaw, list.length))
    list.splice(insertAt, 0, blank)
    const applied = applyWebLocatorToStep(list, insertAt, payload)
    return { steps: applied.steps, updated: applied.updated, stepIndex: insertAt }
  }

  const applied = applyWebLocatorToStep(list, targetIndex, payload)
  return { steps: applied.steps, updated: applied.updated, stepIndex: targetIndex }
}

export function formatLocatorActionSummary(lastResult) {
  if (!lastResult?.type) return ''
  if (lastResult.type === 'highlight') {
    const idx = lastResult.index ?? 1
    const count = lastResult.match_count
    const indexHint = idx > 1 ? `（下标 ${idx}${count != null ? ` / 共 ${count}` : ''}）` : (count != null && count > 1 ? `（匹配 ${count} 个，取第 1 个可见）` : '')
    return lastResult.status === 'success'
      ? `已高亮步骤 ${(lastResult.step_index ?? 0) + 1} 的定位器${indexHint}`
      : `高亮失败：${lastResult.message || ''}`
  }
  if (lastResult.type === 'pick') {
    const frameHint = lastResult.frame ? `（iframe: ${lastResult.frame}）` : ''
    const idx = lastResult.match_index ?? lastResult.meta?.matchIndex ?? 1
    const indexHint = idx > 1 ? `（下标 ${idx}）` : ''
    return `已拾取元素：${lastResult.locator || ''}${frameHint}${indexHint}`
  }
  if (lastResult.type === 'verify') {
    const status = lastResult.status
    const idx = lastResult.index ?? 1
    const indexHint = idx > 1 ? `（下标 ${idx}）` : ''
    if (status === 'success') return `定位器验证通过${indexHint}：${lastResult.message || ''}`
    if (status === 'ambiguous') return `定位器匹配 ${lastResult.match_count} 个${indexHint}：${lastResult.message || ''}`
    return `定位器验证失败${indexHint}：${lastResult.message || ''}`
  }
  if (lastResult.type === 'clear_highlight') {
    return lastResult.message || '已取消高亮'
  }
  return ''
}
