/**
 * AI 需求功能用例 source_ref 解析（文档批次 vs 测试点批次）
 */

/** 筛选用：无 source_ref 的用例（单次早期生成等） */
export const CASE_SOURCE_FILTER_UNLABELED = '__unlabeled__'
/** 筛选用：所有测试点来源（含 test_points / test_points:batch:） */
export const CASE_SOURCE_FILTER_ALL_TEST_POINTS = '__test_points__'

export function parseCaseSourceRef(ref) {
  const s = (ref || '').trim()
  if (!s) return { kind: 'unknown', batchName: '', raw: '' }
  if (s.startsWith('test_points:batch:')) {
    return { kind: 'test_points', batchName: s.slice(19), raw: s }
  }
  if (s === 'test_points') {
    return { kind: 'test_points', batchName: '', raw: s }
  }
  if (s.startsWith('batch:')) {
    return { kind: 'doc', batchName: s.slice(6), raw: s }
  }
  return { kind: 'other', batchName: s, raw: s }
}

export function formatCaseSourceRefLabel(ref) {
  const p = parseCaseSourceRef(ref)
  if (p.kind === 'doc') return p.batchName ? `文档批次：${p.batchName}` : '文档批次'
  if (p.kind === 'test_points') return p.batchName ? `测试点批次：${p.batchName}` : '测试点生成'
  if (p.kind === 'unknown') return '未标注批次'
  return ref || '-'
}

export function isTestPointsSourceRef(ref) {
  return parseCaseSourceRef(ref).kind === 'test_points'
}

export function isCaseInLibraryCopy(c) {
  return ((c?.extra?.library_copies?.length) || 0) > 0
}

/** 按入库状态缩小统计/下拉计数范围 */
export function filterCasesByLibraryStatus(cases, libraryStatus) {
  const list = cases || []
  if (libraryStatus === 'pending') return list.filter(c => !isCaseInLibraryCopy(c))
  if (libraryStatus === 'imported') return list.filter(c => isCaseInLibraryCopy(c))
  return list
}

/**
 * 下拉选项：文档批次 / 测试点批次 / 汇总项；可选条数后缀
 * @returns {{ value: string, label: string, count: number }[]}
 */
export function buildCaseSourceRefOptions(cases, { withCounts = false, libraryStatus = '' } = {}) {
  const pool = filterCasesByLibraryStatus(cases, libraryStatus)
  const refCounts = new Map()
  let unlabeled = 0
  let testPointsTotal = 0

  for (const c of pool) {
    const ref = (c.source_ref || '').trim()
    const p = parseCaseSourceRef(ref)
    if (p.kind === 'unknown') {
      unlabeled += 1
      continue
    }
    if (p.kind === 'test_points') {
      testPointsTotal += 1
      refCounts.set(ref, (refCounts.get(ref) || 0) + 1)
      continue
    }
    refCounts.set(ref, (refCounts.get(ref) || 0) + 1)
  }

  const fmt = (label, count) => (withCounts && count != null ? `${label}（${count}）` : label)
  const opts = []

  for (const [ref, count] of [...refCounts.entries()].sort((a, b) =>
    formatCaseSourceRefLabel(a[0]).localeCompare(formatCaseSourceRefLabel(b[0]), 'zh-CN')
  )) {
    opts.push({
      value: ref,
      label: fmt(formatCaseSourceRefLabel(ref), count),
      count
    })
  }

  if (testPointsTotal > 0) {
    opts.unshift({
      value: CASE_SOURCE_FILTER_ALL_TEST_POINTS,
      label: fmt('全部：测试点生成', testPointsTotal),
      count: testPointsTotal
    })
  }
  if (unlabeled > 0) {
    opts.unshift({
      value: CASE_SOURCE_FILTER_UNLABELED,
      label: fmt('未标注批次（单次生成等）', unlabeled),
      count: unlabeled
    })
  }
  return opts
}

export function caseMatchesSourceFilter(c, sourceRef, pointId) {
  if (sourceRef === CASE_SOURCE_FILTER_UNLABELED) {
    return !(c.source_ref || '').trim()
  }
  if (sourceRef === CASE_SOURCE_FILTER_ALL_TEST_POINTS) {
    return isTestPointsSourceRef(c.source_ref)
  }
  if (sourceRef && (c.source_ref || '') !== sourceRef) return false
  if (pointId) {
    const ids = c.test_point_ids || []
    if (!ids.includes(Number(pointId))) return false
  }
  return true
}

/** 章节 id：选中节与其子/父节双向匹配 */
export function isSectionAncestor(sections, ancestorId, descId) {
  if (!ancestorId || !descId || ancestorId === descId) return false
  const byId = new Map((sections || []).map(s => [s.id, s]))
  let cur = byId.get(descId)
  while (cur?.parent_id) {
    if (cur.parent_id === ancestorId) return true
    cur = byId.get(cur.parent_id)
  }
  return false
}

export function caseMatchesSectionFilter(caseSectionIds, filterSectionId, sections) {
  if (!filterSectionId) return true
  const ids = caseSectionIds || []
  if (!ids.length) return false
  if (ids.includes(filterSectionId)) return true
  return ids.some(
    sid =>
      isSectionAncestor(sections, filterSectionId, sid) ||
      isSectionAncestor(sections, sid, filterSectionId)
  )
}

/** 待审核构成：文档批次 / 测试点 / 未标注 */
export function summarizePendingBySource(cases) {
  let doc = 0
  let testPoints = 0
  let unlabeled = 0
  let other = 0
  const pending = (cases || []).filter(c => !isCaseInLibraryCopy(c))
  for (const c of pending) {
    const p = parseCaseSourceRef(c.source_ref)
    if (p.kind === 'doc') doc += 1
    else if (p.kind === 'test_points') testPoints += 1
    else if (p.kind === 'unknown') unlabeled += 1
    else other += 1
  }
  return { total: pending.length, doc, testPoints, unlabeled, other }
}

/** 与后端 test_points_cases_source_ref 一致 */
export function testPointsCasesSourceRef(batchName) {
  const name = (batchName || '').trim()
  return name ? `test_points:batch:${name}` : 'test_points'
}
