/** Web 步骤备用定位（meta.candidates）规范化与主/备切换 */

export const MAX_LOCATOR_CANDIDATES = 12

export function normalizeLocatorValue(value) {
  const v = String(value || '').trim()
  if (!v) return ''
  if (v.startsWith('xpath=') || v.startsWith('css=') || v.startsWith('text=')) return v
  if (v.startsWith('/') && !v.startsWith('//')) return `xpath=${v}`
  return v
}

export function normalizeCandidates(list, { excludePrimary = '' } = {}) {
  const exclude = normalizeLocatorValue(excludePrimary)
  const seen = new Set()
  const out = []
  for (const item of list || []) {
    let loc = ''
    if (typeof item === 'string') loc = item
    else if (item && typeof item === 'object') {
      loc = item.locator || item.value || item.selector || ''
    }
    loc = normalizeLocatorValue(loc)
    if (!loc || seen.has(loc)) continue
    if (exclude && loc === exclude) continue
    seen.add(loc)
    out.push(loc)
    if (out.length >= MAX_LOCATOR_CANDIDATES) break
  }
  return out
}

/** 将某条备用提升为主定位；原主插入备用队首 */
export function promoteToPrimary(primary, candidates, nextPrimary) {
  const next = normalizeLocatorValue(nextPrimary)
  const prev = normalizeLocatorValue(primary)
  if (!next) {
    return { primary: prev, candidates: normalizeCandidates(candidates, { excludePrimary: prev }) }
  }
  const rest = normalizeCandidates(candidates, { excludePrimary: next })
  if (prev && prev !== next) {
    rest.unshift(prev)
  }
  return {
    primary: next,
    candidates: normalizeCandidates(rest, { excludePrimary: next }),
  }
}

/** 助手结果：写主 + 合并其余为备用 */
export function mergeAssistIntoStep(primary, candidates, assistItems, { applyAll = true } = {}) {
  const items = (assistItems || [])
    .map((c) => (typeof c === 'string' ? c : c?.locator))
    .map(normalizeLocatorValue)
    .filter(Boolean)
  if (!items.length) {
    return {
      primary: normalizeLocatorValue(primary),
      candidates: normalizeCandidates(candidates, { excludePrimary: primary }),
    }
  }
  const nextPrimary = items[0]
  if (!applyAll) {
    return promoteToPrimary(primary, candidates, nextPrimary)
  }
  const rest = items.slice(1)
  const merged = normalizeCandidates(
    [...rest, ...(candidates || [])],
    { excludePrimary: nextPrimary },
  )
  const prev = normalizeLocatorValue(primary)
  if (prev && prev !== nextPrimary && !merged.includes(prev)) {
    merged.push(prev)
  }
  return {
    primary: nextPrimary,
    candidates: normalizeCandidates(merged, { excludePrimary: nextPrimary }),
  }
}
