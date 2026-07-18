/** 用例编辑页：从 execution-hints 接口结果取某一步的失败信息 */
export function parseExecutionIdQuery(raw) {
  if (raw == null || raw === '') return undefined
  const id = Number(raw)
  return Number.isFinite(id) && id > 0 ? id : undefined
}

export function getStepExecutionHint(executionHints, stepIndex) {
  if (!executionHints?.step_failures?.length) return null
  const idx = Number(stepIndex)
  const matches = executionHints.step_failures.filter((item) => Number(item.step_index) === idx)
  if (!matches.length) return null
  return matches.find((item) => ['fail', 'failed', 'error'].includes(String(item?.status || '').toLowerCase()))
    || matches[matches.length - 1]
}

export function formatExecutionHintStatus(status) {
  const key = String(status || '').toLowerCase()
  if (key === 'error') return '执行错误'
  if (key === 'fail' || key === 'failed') return '执行失败'
  return '执行异常'
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
