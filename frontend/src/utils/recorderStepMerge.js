/**
 * 录制结果合并到已有步骤（W-11 / W-31）
 * @param {Array} existingSteps
 * @param {Array} newSteps
 * @param {'replace'|'append'|'insert'} mode
 * @param {number|null} insertAtIndex 插入位置（新步骤写入 index，其后原步骤顺延）
 */
export function mergeRecorderSteps(existingSteps, newSteps, mode = 'replace', insertAtIndex = null) {
  const existing = Array.isArray(existingSteps) ? existingSteps : []
  const incoming = Array.isArray(newSteps) ? newSteps : []
  if (!incoming.length) return [...existing]
  if (mode === 'replace') return JSON.parse(JSON.stringify(incoming))
  if (mode === 'append') return [...existing, ...JSON.parse(JSON.stringify(incoming))]
  if (mode === 'insert') {
    const at = insertAtIndex == null
      ? existing.length
      : Math.max(0, Math.min(Number(insertAtIndex) || 0, existing.length))
    return [
      ...existing.slice(0, at),
      ...JSON.parse(JSON.stringify(incoming)),
      ...existing.slice(at),
    ]
  }
  return JSON.parse(JSON.stringify(incoming))
}

export function resolveRecorderApplyModeLabel(mode) {
  if (mode === 'append') return '追加到末尾'
  if (mode === 'insert') return '插入到指定位置'
  return '覆盖全部步骤'
}
