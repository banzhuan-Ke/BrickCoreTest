/** UI Agent Job 通用展示辅助 */

export function meaningfulUiAgentSteps(steps) {
  return (steps || []).filter(
    (s) => s?.method && !['open_browser', 'open_url'].includes(s.method)
  )
}

export function uiAgentJobHasUsableSteps(job) {
  const steps = job?.steps
  return Array.isArray(steps) && steps.length > 0
}

export function isUiAgentJobTerminalSuccess(job) {
  const status = job?.status
  return status === 'done' || status === 'stopped'
}

/** 终态是否应展示/保留步骤（含 guard 误判 failed 但已有步骤） */
export function shouldPresentUiAgentSteps(job) {
  return isUiAgentJobTerminalSuccess(job)
    || (job?.status === 'failed' && uiAgentJobHasUsableSteps(job))
}

export function warnIfUiAgentStepsSparse(steps, ElMessage, options = {}) {
  const meaningful = meaningfulUiAgentSteps(steps)
  const min = options.minMeaningfulSteps ?? 6
  if (meaningful.length > 0 && meaningful.length < min) {
    ElMessage.warning(
      options.message
        || `Agent 仅产出 ${meaningful.length} 步有效操作，可能未完整执行多步目标，请核对后再导入/保存`
    )
    return true
  }
  return false
}

/**
 * 统一处理 Agent 任务终态提示（成功 / 部分成功 / 无步骤）。
 * @returns {{ ok: boolean, partial: boolean }}
 */
export function notifyUiAgentJobOutcome(job, ElMessage, options = {}) {
  const steps = job?.steps || []
  if (!shouldPresentUiAgentSteps(job)) {
    ElMessage.error(job?.error_message || options.failMessage || 'Agent 探索失败')
    return { ok: false, partial: false }
  }
  if (!steps.length) {
    ElMessage.warning(options.emptyStepsMessage || '探索完成但未产出步骤')
    return { ok: false, partial: false }
  }
  if (job?.status === 'failed') {
    ElMessage.warning(
      job.error_message
        || options.partialMessage
        || 'Agent 探索未完整完成，可核对步骤后仍尝试导入/保存'
    )
    return { ok: true, partial: true }
  }
  if (options.warnSparse !== false) {
    warnIfUiAgentStepsSparse(steps, ElMessage, options.sparseOptions)
  }
  if (options.successMessage) {
    ElMessage.success(options.successMessage)
  }
  return { ok: true, partial: false }
}
