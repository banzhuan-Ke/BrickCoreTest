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

/** 根据拾取元素类型推荐步骤关键字模板 */
export function suggestPickStepTemplate(meta = {}) {
  const tag = String(meta.tag || '').toLowerCase()
  const inputType = String(meta.inputType || '').toLowerCase()
  const cls = String(meta.class || meta.role || '').toLowerCase()
  if (tag === 'input' || tag === 'textarea' || inputType === 'text' || inputType === 'password') {
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

  const nextParams = {
    ...step.params,
    index: matchIndex,
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
    const template = options.template || suggestPickStepTemplate(payload.meta || payload.element || {})
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
  if (lastResult.type === 'verify') {
    const status = lastResult.status
    if (status === 'success') return `定位器验证通过：${lastResult.message || ''}`
    if (status === 'ambiguous') return `定位器匹配 ${lastResult.match_count} 个：${lastResult.message || ''}`
    return `定位器验证失败：${lastResult.message || ''}`
  }
  if (lastResult.type === 'highlight') {
    return lastResult.status === 'success'
      ? `已高亮步骤 ${(lastResult.step_index ?? 0) + 1} 的定位器`
      : `高亮失败：${lastResult.message || ''}`
  }
  if (lastResult.type === 'pick') {
    const frameHint = lastResult.frame ? `（iframe: ${lastResult.frame}）` : ''
    return `已拾取元素：${lastResult.locator || ''}${frameHint}`
  }
  if (lastResult.type === 'clear_highlight') {
    return lastResult.message || '已取消高亮'
  }
  return ''
}
