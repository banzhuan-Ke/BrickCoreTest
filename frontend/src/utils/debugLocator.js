/** 交互调试：定位器回填与步骤能力判断 */
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
  return ''
}
