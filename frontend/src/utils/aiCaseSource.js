/**
 * AI 需求功能用例 source_ref 解析（文档批次 vs 测试点批次）
 */

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
  return ref || '-'
}

export function isTestPointsSourceRef(ref) {
  return parseCaseSourceRef(ref).kind === 'test_points'
}

/** 下拉选项：{ value: 完整 source_ref, label } */
export function buildCaseSourceRefOptions(cases) {
  const seen = new Set()
  const opts = []
  for (const c of cases || []) {
    const ref = (c.source_ref || '').trim()
    if (!ref || seen.has(ref)) continue
    seen.add(ref)
    opts.push({ value: ref, label: formatCaseSourceRefLabel(ref) })
  }
  return opts.sort((a, b) => a.label.localeCompare(b.label, 'zh-CN'))
}

export function caseMatchesSourceFilter(c, sourceRef, pointId) {
  if (sourceRef && (c.source_ref || '') !== sourceRef) return false
  if (pointId) {
    const ids = c.test_point_ids || []
    if (!ids.includes(Number(pointId))) return false
  }
  return true
}

/** 与后端 test_points_cases_source_ref 一致 */
export function testPointsCasesSourceRef(batchName) {
  const name = (batchName || '').trim()
  return name ? `test_points:batch:${name}` : 'test_points'
}
