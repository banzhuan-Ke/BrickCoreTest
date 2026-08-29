export function hasQuarantineTag(tags) {
  if (tags == null) return false
  if (typeof tags === 'string') {
    return tags.split(',').some((t) => String(t || '').trim().toLowerCase() === 'quarantine')
  }
  if (Array.isArray(tags)) {
    return tags.some((t) => String(t || '').trim().toLowerCase() === 'quarantine')
  }
  return false
}

export function isCaseQuarantined(row, stabilityItem) {
  if (row?.quarantine) return true
  if (stabilityItem?.quarantine) return true
  return hasQuarantineTag(row?.tags)
}
