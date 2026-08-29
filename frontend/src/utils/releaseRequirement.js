/** 从版本需求列表中解析预览目标 */
export function parseAiRequirementId(requirementKey) {
  const m = String(requirementKey || '').match(/^REQ-(\d+)$/i)
  return m ? Number(m[1]) : null
}

/** 是否为项目需求（REQ-{id} 或已关联 ai_requirement_id） */
export function isProjectRequirement(row) {
  if (!row) return false
  if (row.source_type === 'ai') return true
  if (row.ai_requirement_id) return true
  return !!parseAiRequirementId(row.requirement_key)
}

export function requirementTypeLabel(row) {
  return isProjectRequirement(row) ? '项目' : '外部'
}

export function findReleaseRequirement(requirements, { requirementKey, aiRequirementId } = {}) {
  const list = Array.isArray(requirements) ? requirements : []
  if (aiRequirementId) {
    const id = Number(aiRequirementId)
    const key = `REQ-${id}`
    return (
      list.find((r) => Number(r.ai_requirement_id) === id) ||
      list.find((r) => String(r.requirement_key || '').toUpperCase() === key)
    )
  }
  const key = String(requirementKey || '').trim()
  if (!key) return null
  return list.find((r) => String(r.requirement_key || '').trim() === key) || null
}

export function excerptAroundContent(text, needle, radius = 600) {
  const src = String(text || '')
  const q = String(needle || '').trim()
  if (!src || !q) return src.slice(0, radius * 2)
  const idx = src.indexOf(q)
  if (idx < 0) return src.slice(0, radius * 2)
  const start = Math.max(0, idx - radius)
  const end = Math.min(src.length, idx + q.length + radius)
  let chunk = src.slice(start, end)
  if (start > 0) chunk = `…${chunk}`
  if (end < src.length) chunk = `${chunk}…`
  return chunk
}
