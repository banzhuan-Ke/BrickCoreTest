/** Web 步骤备用定位（meta.candidates）规范化与主/备切换
 * 与 backend/runner locator_candidate_contract 语义对齐：
 * - source: current | elevated | neighbor | ai
 * - 默认主定位 = best(current)；无 current 时返回空（不偷换）
 * - 落盘截断保住 primary，并尽量各 source 至少一条
 * - 同 locator 多 source 去重优先保留 current
 * - locator 形态：/html → xpath=/html
 */

export const MAX_LOCATOR_CANDIDATES = 12

export const LOCATOR_SOURCE_LABELS = {
  current: '当前所选',
  elevated: '抬升',
  neighbor: '相邻',
  ai: 'AI 建议',
}

/** 分组展示顺序 */
export const LOCATOR_SOURCE_ORDER = ['current', 'elevated', 'neighbor', 'ai']

/** 分组标题旁问号说明 */
export const LOCATOR_SOURCE_TIPS = {
  current: '你实际点中（或当前主定位）元素上的定位写法，忠实命中；默认作为主定位，不会被抬升/相邻自动替换。',
  elevated: '从点中元素抬升到更稳的宿主（如菜单项、下拉项），仅作备用推荐，需你手动选用才会成为主定位。',
  neighbor: '用相邻明显文案锚定到目标（如标签旁的问号/图标），适合点中的是图标本身时作备用。',
  ai: 'AI 建议或自愈生成的定位，需确认后再采用。',
}

export const PRIMARY_DECISION = {
  faithful_hit: 'faithful_hit',
  user_selected: 'user_selected',
  healed: 'healed',
  assist: 'assist',
}

const PRIMARY_DECISIONS = new Set(Object.values(PRIMARY_DECISION))

export function normalizeDecision(decision) {
  const d = String(decision || PRIMARY_DECISION.faithful_hit).trim().toLowerCase().replace(/-/g, '_')
  return PRIMARY_DECISIONS.has(d) ? d : PRIMARY_DECISION.faithful_hit
}

export function normalizeLocatorValue(value) {
  const v = String(value || '').trim()
  if (!v) return ''
  if (v.includes('||')) {
    const idx = v.indexOf('||')
    const frame = v.slice(0, idx)
    const rest = v.slice(idx + 2)
    return rest ? `${frame}||${normalizeLocatorValue(rest)}` : v
  }
  if (v.startsWith('xpath=') || v.startsWith('css=') || v.startsWith('text=')) return v
  if (v.startsWith('/') && !v.startsWith('//')) return `xpath=${v}`
  return v
}

/** 从候选项（字符串或 {locator, source}）取出定位串 */
export function candidateLocatorOf(item) {
  if (item == null) return ''
  if (typeof item === 'string') return normalizeLocatorValue(item)
  if (typeof item === 'object') {
    return normalizeLocatorValue(item.locator || item.value || item.selector || '')
  }
  return normalizeLocatorValue(item)
}

/** 候选来源：current | elevated | neighbor | ai（rule→current） */
export function candidateSourceOf(item) {
  if (item && typeof item === 'object') {
    let s = String(item.source || 'current').trim().toLowerCase()
    if (s === 'rule' || s === 'params.locator' || s === 'params.candidates' || s === 'meta.candidates') {
      s = 'current'
    }
    if (s === 'elevated' || s === 'neighbor' || s === 'current' || s === 'ai') return s
  }
  return 'current'
}

export function candidateSourceLabel(item) {
  return LOCATOR_SOURCE_LABELS[candidateSourceOf(item)] || LOCATOR_SOURCE_LABELS.current
}

function preferSourceForDedup(oldSrc, newSrc) {
  const oldS = candidateSourceOf({ source: oldSrc })
  const newS = candidateSourceOf({ source: newSrc })
  if (oldS === newS) return oldS
  // 忠实命中池：current 优先于 elevated/neighbor/ai
  if (oldS === 'current' || newS === 'current') return 'current'
  return oldS
}

/**
 * 规范化候选列表。
 * keepObjects=false（默认）：只返回定位字符串（兼容旧逻辑）
 * keepObjects=true：保留 {locator, source}
 * maxN=null：不截断
 */
export function normalizeCandidates(list, {
  excludePrimary = '',
  keepObjects = false,
  maxN = MAX_LOCATOR_CANDIDATES,
} = {}) {
  const exclude = normalizeLocatorValue(excludePrimary)
  const seen = new Map()
  const out = []
  const unlimited = maxN == null
  const limit = unlimited ? Infinity : Math.max(1, Number(maxN) || MAX_LOCATOR_CANDIDATES)
  for (const item of list || []) {
    const loc = candidateLocatorOf(item)
    if (!loc) continue
    if (exclude && loc === exclude) continue
    const src = candidateSourceOf(item)
    if (seen.has(loc)) {
      const idx = seen.get(loc)
      const kept = preferSourceForDedup(out[idx].source || out[idx], src)
      if (keepObjects && kept !== out[idx].source) {
        out[idx] = { locator: loc, source: kept }
      }
      continue
    }
    seen.set(loc, out.length)
    if (keepObjects) {
      out.push({ locator: loc, source: src })
    } else {
      out.push(loc)
    }
    if (out.length >= limit) break
  }
  return out
}

/** 主定位只从 current 取；无 current 返回空（不偷换 elevated/neighbor） */
export function pickDefaultFromCandidates(list, { allowNonCurrentFallback = false } = {}) {
  const items = normalizeCandidates(list, { keepObjects: true, maxN: null })
  const currents = items.filter((c) => c.source === 'current')
  if (currents.length) return currents[0].locator
  if (allowNonCurrentFallback) return items[0]?.locator || ''
  return ''
}

export function resolvePrimarySource(primary, candidates, explicit) {
  if (explicit != null && String(explicit).trim()) {
    return candidateSourceOf({ source: explicit })
  }
  const loc = normalizeLocatorValue(primary)
  if (!loc) return 'current'
  const hit = (candidates || []).find((c) => candidateLocatorOf(c) === loc)
  return hit ? candidateSourceOf(hit) : 'current'
}

export function pickRecommendedCandidate(candidates, excludePrimary = '') {
  const exclude = normalizeLocatorValue(excludePrimary)
  for (const item of normalizeCandidates(candidates, { keepObjects: true, maxN: null })) {
    if (item.source === 'current') continue
    if (exclude && item.locator === exclude) continue
    const reason =
      item.source === 'elevated'
        ? '更稳定的抬升宿主'
        : item.source === 'neighbor'
          ? '相邻明显文案锚定'
          : item.source === 'ai'
            ? 'AI 建议定位'
            : '备选定位'
    return { locator: item.locator, source: item.source, reason }
  }
  return null
}

/** 落盘截断：保住 primary，并尽量各 source 一条 */
export function trimCandidatesForStorage(list, primary = '', maxN = MAX_LOCATOR_CANDIDATES) {
  const all = normalizeCandidates(list, { keepObjects: true, maxN: null })
  const limit = Math.max(1, Number(maxN) || MAX_LOCATOR_CANDIDATES)
  const primaryLoc = normalizeLocatorValue(primary)
  const out = []
  const seen = new Set()
  const push = (row) => {
    if (!row?.locator || seen.has(row.locator) || out.length >= limit) return
    seen.add(row.locator)
    out.push({ locator: row.locator, source: candidateSourceOf(row) })
  }
  if (primaryLoc) {
    const hit = all.find((c) => c.locator === primaryLoc)
    push(hit || { locator: primaryLoc, source: 'current' })
  }
  for (const key of ['current', 'elevated', 'neighbor', 'ai']) {
    const hit = all.find((c) => c.source === key && !seen.has(c.locator))
    if (hit) push(hit)
  }
  for (const row of all) {
    if (out.length >= limit) break
    push(row)
  }
  return out
}

export function applyPrimaryMetaFields(meta, candidates, primary, {
  decision = PRIMARY_DECISION.faithful_hit,
  primarySource = null,
  clearCandidatesIfEmpty = true,
} = {}) {
  const out = { ...(meta || {}) }
  const primaryLoc = normalizeLocatorValue(primary)
  const raw = candidates
  let cands = normalizeCandidates(raw == null ? (out.candidates || []) : raw, {
    keepObjects: true,
    maxN: null,
  })
  const decisionN = normalizeDecision(decision)
  let src = resolvePrimarySource(primaryLoc, cands, primarySource)
  if (decisionN === PRIMARY_DECISION.faithful_hit && primarySource == null) {
    src = 'current'
  }
  out.primarySource = src
  out.primaryDecision = decisionN

  if (Array.isArray(raw) && raw.length === 0 && clearCandidatesIfEmpty) {
    delete out.candidates
    delete out.recommended
    return out
  }

  if (primaryLoc) {
    const idx = cands.findIndex((c) => c.locator === primaryLoc)
    if (idx >= 0) cands[idx] = { locator: primaryLoc, source: src }
    else cands = [{ locator: primaryLoc, source: src }, ...cands]
  }
  const trimmed = trimCandidatesForStorage(cands, primaryLoc)
  if (trimmed.length) out.candidates = trimmed
  else if (clearCandidatesIfEmpty) delete out.candidates

  const rec = pickRecommendedCandidate(cands, primaryLoc)
  if (rec && rec.locator !== primaryLoc) out.recommended = rec
  else delete out.recommended
  return out
}

/**
 * 将某条备用提升为主定位。
 * @param {string} primary
 * @param {Array} candidates 可不含旧 primary
 * @param {string|object} nextPrimary
 * @param {{ primarySource?: string }} opts 旧主定位来源，避免降成 current
 */
export function promoteToPrimary(primary, candidates, nextPrimary, opts = {}) {
  const next = normalizeLocatorValue(
    typeof nextPrimary === 'object' ? candidateLocatorOf(nextPrimary) : nextPrimary,
  )
  const prev = normalizeLocatorValue(primary)
  const nextSource =
    typeof nextPrimary === 'object'
      ? candidateSourceOf(nextPrimary)
      : resolvePrimarySource(next, candidates)
  const prevSource = opts.primarySource
    ? candidateSourceOf({ source: opts.primarySource })
    : resolvePrimarySource(prev, candidates)

  if (!next) {
    const rest = normalizeCandidates(candidates, { excludePrimary: prev, keepObjects: true, maxN: null })
    return {
      primary: prev,
      candidates: trimCandidatesForStorage(rest, prev),
      primarySource: prevSource || 'current',
      primaryDecision: PRIMARY_DECISION.faithful_hit,
      recommended: pickRecommendedCandidate(rest, prev),
    }
  }

  const rest = normalizeCandidates(candidates, { excludePrimary: next, keepObjects: true, maxN: null })
  if (prev && prev !== next) {
    rest.unshift({ locator: prev, source: prevSource || 'current' })
  }
  const merged = trimCandidatesForStorage(rest, next)
  return {
    primary: next,
    candidates: merged,
    primarySource: nextSource || 'current',
    primaryDecision: PRIMARY_DECISION.user_selected,
    recommended: pickRecommendedCandidate(
      [{ locator: next, source: nextSource }, ...merged],
      next,
    ),
  }
}

/** 助手结果：写主 + 合并其余为备用（保留 source） */
export function mergeAssistIntoStep(primary, candidates, assistItems, {
  applyAll = true,
  primarySource = 'current',
} = {}) {
  const items = (assistItems || [])
    .map((c) => ({
      locator: candidateLocatorOf(c),
      source: candidateSourceOf(c),
    }))
    .filter((c) => c.locator)
  if (!items.length) {
    return {
      primary: normalizeLocatorValue(primary),
      candidates: normalizeCandidates(candidates, { keepObjects: true }),
      primarySource: resolvePrimarySource(primary, candidates, primarySource),
      primaryDecision: PRIMARY_DECISION.assist,
    }
  }
  if (!applyAll) {
    return promoteToPrimary(primary, candidates, items[0], { primarySource })
  }
  const nextPrimary = items[0]
  const rest = items.slice(1)
  const prev = normalizeLocatorValue(primary)
  const merged = normalizeCandidates(
    [...rest, ...(candidates || [])],
    { excludePrimary: nextPrimary.locator, keepObjects: true, maxN: null },
  )
  if (prev && prev !== nextPrimary.locator) {
    merged.unshift({
      locator: prev,
      source: candidateSourceOf({ source: primarySource }) || 'current',
    })
  }
  return {
    primary: nextPrimary.locator,
    candidates: trimCandidatesForStorage(merged, nextPrimary.locator),
    primarySource: nextPrimary.source || 'ai',
    primaryDecision: PRIMARY_DECISION.assist,
    recommended: pickRecommendedCandidate(
      [nextPrimary, ...merged],
      nextPrimary.locator,
    ),
  }
}

/**
 * 按来源分组（仅返回有条目的组），供拾取弹窗 / 助手列表展示。
 * @returns {{ source: string, label: string, tip: string, items: Array }[]}
 */
export function groupCandidatesBySource(list) {
  const buckets = {
    current: [],
    elevated: [],
    neighbor: [],
    ai: [],
  }
  for (const item of normalizeCandidates(list, { keepObjects: true, maxN: null })) {
    const src = candidateSourceOf(item)
    if (buckets[src]) buckets[src].push(item)
    else buckets.current.push(item)
  }
  return LOCATOR_SOURCE_ORDER
    .filter((key) => buckets[key].length)
    .map((key) => ({
      source: key,
      label: LOCATOR_SOURCE_LABELS[key],
      tip: LOCATOR_SOURCE_TIPS[key] || '',
      items: buckets[key],
    }))
}

function _xpathStringLiteral(text) {
  const s = String(text || '').trim()
  if (!s) return ''
  if (!s.includes("'")) return `'${s}'`
  if (!s.includes('"')) return `"${s}"`
  return null
}

function _neighborRelAxis(climb, neighborRel, tTag, siblingIdx) {
  const step = `${neighborRel}::${tTag}[${siblingIdx}]`
  if (climb <= 0) return step
  return `ancestor::*[${climb}]/${step}`
}

/**
 * 与 Backend/Runner 对齐：按 meta.neighbor* + neighborClimb 生成相邻候选。
 * climb 未知时试 0/1；有 cssPath 稳定 #id 时加作用域。
 */
export function buildNeighborCandidatesFromMeta(meta = {}) {
  const neighborText = String(meta.neighborText || '').trim()
  const neighborRel = String(meta.neighborRelation || '').trim()
  const neighborTag = String(meta.neighborTag || '*').trim() || '*'
  const tag = String(meta.neighborTargetTag || meta.tag || '*').trim() || '*'
  let siblingIdx = 1
  try {
    siblingIdx = Math.max(1, parseInt(meta.neighborSiblingIndex || 1, 10) || 1)
  } catch (_) { /* ignore */ }
  if (
    !neighborText
    || !['following-sibling', 'preceding-sibling'].includes(neighborRel)
    || neighborText.length <= 1
    || neighborText.length > 40
  ) {
    return []
  }
  const nLit = _xpathStringLiteral(neighborText)
  if (!nLit) return []
  const nTag = neighborTag.replace(/[^a-zA-Z0-9_-]/g, '') || '*'
  const tTag = tag.replace(/[^a-zA-Z0-9_-]/g, '') || '*'
  let climbs = [0, 1]
  if (meta.neighborClimb != null && String(meta.neighborClimb).trim() !== '') {
    const c = parseInt(meta.neighborClimb, 10)
    if (Number.isFinite(c)) climbs = [Math.max(0, Math.min(8, c))]
  }
  const leaf = `//${nTag}[normalize-space()=${nLit}][not(.//${nTag}[normalize-space()=${nLit}])]`
  const out = []
  for (const climb of climbs) {
    const axis = _neighborRelAxis(climb, neighborRel, tTag, siblingIdx)
    out.push(`get_by_text=${neighborText} >> xpath=./${axis}`)
    out.push(`xpath=${leaf}/${axis}`)
  }
  const css = String(meta.cssPath || '').trim()
  const m = css.match(/^(#[^\s>#]+)/)
  if (m) {
    const scope = m[1]
    const scoped = []
    for (const climb of climbs) {
      const axis = _neighborRelAxis(climb, neighborRel, tTag, siblingIdx)
      scoped.push(`${scope} >> get_by_text=${neighborText} >> xpath=./${axis}`)
      scoped.push(`${scope} >> xpath=.${leaf}/${axis}`)
    }
    return [...scoped, ...out]
  }
  return out
}

/**
 * 自愈落盘：新 locator=ai，旧失败=current，重算相邻，保留抬升。
 */
export function mergeHealedLocatorCandidates({
  healed,
  failed,
  existingCandidates = [],
  meta = {},
} = {}) {
  const next = normalizeLocatorValue(healed)
  const prev = normalizeLocatorValue(failed)
  const keep = []
  const seen = new Set()
  const push = (loc, source) => {
    const n = normalizeLocatorValue(loc)
    if (!n || seen.has(n) || n === next) return
    seen.add(n)
    keep.push({ locator: n, source: candidateSourceOf({ source }) })
  }
  if (prev && prev !== next) push(prev, 'current')
  for (const c of existingCandidates || []) {
    const loc = candidateLocatorOf(c)
    const src = candidateSourceOf(c)
    if (src === 'neighbor') continue // 用 climb 规则重算
    if (src === 'elevated' || src === 'ai' || src === 'current') push(loc, src)
  }
  for (const loc of buildNeighborCandidatesFromMeta(meta)) {
    push(loc, 'neighbor')
  }
  return trimCandidatesForStorage(
    [{ locator: next, source: 'ai' }, ...keep],
    next,
  )
}
