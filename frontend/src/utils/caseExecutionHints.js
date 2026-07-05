/** 用例编辑页：从 execution-hints 接口结果取某一步的失败信息 */
export function parseExecutionIdQuery(raw) {
  if (raw == null || raw === '') return undefined
  const id = Number(raw)
  return Number.isFinite(id) && id > 0 ? id : undefined
}

export function getStepExecutionHint(executionHints, stepIndex) {
  if (!executionHints?.step_failures?.length) return null
  const idx = Number(stepIndex)
  return executionHints.step_failures.find((item) => Number(item.step_index) === idx) || null
}

export function formatExecutionHintStatus(status) {
  const key = String(status || '').toLowerCase()
  if (key === 'error') return '执行错误'
  if (key === 'fail' || key === 'failed') return '执行失败'
  return '执行异常'
}
