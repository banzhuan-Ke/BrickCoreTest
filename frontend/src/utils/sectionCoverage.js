/**
 * 与 backend compute_section_coverage 保持一致，供前端本地计算章节覆盖。
 */
export function computeSectionCoverage(allSections, cases) {
  if (!allSections?.length) {
    return {
      total: 0,
      covered_count: 0,
      uncovered_count: 0,
      covered_section_ids: [],
      uncovered_sections: []
    }
  }

  const allIds = new Set(allSections.map(s => s.id).filter(Boolean))
  const covered = new Set()

  for (const c of cases || []) {
    for (const sid of c.section_ids || []) {
      if (allIds.has(sid)) covered.add(sid)
    }
  }

  const childrenMap = {}
  for (const sec of allSections) {
    const sid = sec.id
    const pid = sec.parent_id
    if (sid && pid) {
      if (!childrenMap[pid]) childrenMap[pid] = []
      childrenMap[pid].push(sid)
    }
  }

  let changed = true
  while (changed) {
    changed = false
    for (const sid of allIds) {
      if (covered.has(sid)) continue
      const kids = (childrenMap[sid] || []).filter(k => allIds.has(k))
      if (kids.length && kids.every(k => covered.has(k))) {
        covered.add(sid)
        changed = true
      }
    }
  }

  const uncovered = allSections.filter(s => s.id && !covered.has(s.id))
  return {
    total: allIds.size,
    covered_count: covered.size,
    uncovered_count: uncovered.length,
    covered_section_ids: [...covered].sort(),
    uncovered_sections: uncovered.map(s => ({
      id: s.id,
      title: s.title,
      level: s.level
    }))
  }
}

export function applyPendingSectionProjection(coverage, sections, pendingSectionIds) {
  if (!pendingSectionIds?.length || !coverage) return coverage
  const allIds = new Set(sections.map(s => s.id).filter(Boolean))
  const pending = new Set(pendingSectionIds.filter(id => allIds.has(id)))
  const projected = new Set([...coverage.covered_section_ids, ...pending])
  return {
    ...coverage,
    pending_section_ids: [...pending].sort(),
    projected_covered_count: projected.size,
    projected_uncovered_count: allIds.size - projected.size
  }
}
