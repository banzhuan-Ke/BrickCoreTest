export const ELEMENT_LOCATOR_METHODS = new Set(['click_ele', 'fill_value', 'select_option', 'hover_ele'])

export function importModeFromRecommended(recommended) {
  if (recommended === 'solidify') return 'agent'
  return 'draft'
}

export function draftStepsSourceFromRecommended(recommended) {
  if (recommended === 'quick_cache') return 'cache'
  return 'steps'
}

export function qualityTag(step) {
  const meta = step?.meta || {}
  if (meta.locator_strength === 'strong') return { type: 'success', text: '强' }
  if (meta.candidates?.length) return { type: 'primary', text: `候选×${meta.candidates.length}` }
  if (meta.needs_manual_locator || meta.locator_strength === 'weak') {
    return { type: 'warning', text: '需核对' }
  }
  if (meta.locator_strength === 'heuristic') return { type: 'info', text: '启发' }
  return { type: 'info', text: '-' }
}

export function isLocatorStep(step) {
  return ELEMENT_LOCATOR_METHODS.has(step?.method)
}

export function paramPreview(row) {
  const p = row?.params || {}
  if (p.url) return p.url
  if (p.locator) return p.locator
  if (p.value != null && p.value !== '') return String(p.value)
  return JSON.stringify(p).slice(0, 80)
}

export function onLocatorChange(step, locator) {
  if (!step?.params) step.params = {}
  step.params.locator = locator
}

export function onLocatorMetaChange(step, meta) {
  step.meta = meta
}
