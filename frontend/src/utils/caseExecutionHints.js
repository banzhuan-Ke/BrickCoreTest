/** 用例编辑页：从 execution-hints 接口结果取某一步的失败信息 */
export function parseExecutionIdQuery(raw) {
  if (raw == null || raw === '') return undefined
  const id = Number(raw)
  return Number.isFinite(id) && id > 0 ? id : undefined
}

function pickPreferredFailure(matches) {
  if (!matches?.length) return null
  return matches.find((item) => ['fail', 'failed', 'error'].includes(String(item?.status || '').toLowerCase()))
    || matches[matches.length - 1]
}

function pickPreferredRecovery(matches) {
  if (!matches?.length) return null
  return matches[matches.length - 1]
}

function matchHintEntries(entries, stepIndex, step = null) {
  const list = (entries || []).filter((item) => item && !item.unresolved)
  if (!list.length) return []

  const stepId = step?.id != null ? String(step.id).trim() : ''
  if (stepId) {
    const byId = list.filter((item) => item.step_id && String(item.step_id).trim() === stepId)
    if (byId.length) return byId
  }

  const idx = Number(stepIndex)
  return list.filter((item) => Number(item.step_index) === idx)
}

/**
 * @param {object|null} executionHints
 * @param {number} stepIndex 编辑器步骤下标（0-based）
 * @param {object|null} step 当前步骤对象（优先用 step.id 对齐历史失败）
 */
export function getStepExecutionHint(executionHints, stepIndex, step = null) {
  if (!executionHints?.step_failures?.length) return null
  return pickPreferredFailure(matchHintEntries(executionHints.step_failures, stepIndex, step))
}

/**
 * 自愈 / AI Act 成功救回提示（与失败提示独立）
 */
export function getStepRecoveryHint(executionHints, stepIndex, step = null) {
  if (!executionHints?.step_recoveries?.length) return null
  return pickPreferredRecovery(matchHintEntries(executionHints.step_recoveries, stepIndex, step))
}

export function formatExecutionHintStatus(status) {
  const key = String(status || '').toLowerCase()
  if (key === 'error') return '执行错误'
  if (key === 'fail' || key === 'failed') return '执行失败'
  return '执行异常'
}

export function hasExecutionHintsPayload(payload) {
  if (!payload) return false
  if (payload.has_failure) return true
  if (payload.has_recovery) return true
  if (payload.step_recoveries?.some((r) => r && !r.unresolved)) return true
  return false
}

/** 从报告 result_data 解析失败步下标（0-based），供 W-14 跳转交互调试 */
export function resolveFailedStepIndexFromResult(resultData) {
  const rd = resultData || {}
  const steps = rd.steps || []
  for (let i = 0; i < steps.length; i++) {
    const st = String(steps[i]?.status || '').toLowerCase()
    if (['fail', 'failed', 'error'].includes(st)) return i
  }
  let raw = rd.failed_step_index ?? rd.summary?.failed_step_index
  if (raw == null) return undefined
  const n = Number(raw)
  if (!Number.isFinite(n)) return undefined
  if (n >= 1) return n - 1
  if (n >= 0) return n
  return undefined
}
