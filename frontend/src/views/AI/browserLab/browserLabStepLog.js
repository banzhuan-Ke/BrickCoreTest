/** 智能浏览器 step_log 展示辅助（Runner / browser-use 步号与平台 UI 对齐） */

export function isBootstrapStep(step) {
  return Number(step?.index) === 0 || step?.step_status === 'bootstrap'
}

export function isFailedStep(step) {
  return step?.step_status === 'failed' || step?.step_status === 'recovered'
}

/** 列表展示：去掉 bootstrap，按 index 排序（兼容 report.steps 无 type 字段） */
export function normalizeBrowserLabSteps(stepLog) {
  const steps = (stepLog || []).filter((e) => {
    if (e?.type && e.type !== 'step') return false
    return !isBootstrapStep(e)
  })
  return [...steps].sort((a, b) => Number(a.index || 0) - Number(b.index || 0))
}

export function browserLabStepLabel(step) {
  const idx = Number(step?.index)
  if (isBootstrapStep(step)) return '启动'
  if (Number.isFinite(idx) && idx > 0) return `Step ${idx}`
  return 'Step'
}

export function browserLabStepTagType(step) {
  if (isBootstrapStep(step)) return 'info'
  if (step?.step_status === 'failed') return 'danger'
  if (step?.step_status === 'recovered') return 'warning'
  return 'primary'
}

/** 执行中顶部一行状态（避免 Step 0 文案一直占满日志） */
export function browserLabLiveHint(steps, { running = false, status = '' } = {}) {
  if (!running && ['done', 'failed', 'stopped'].includes(status)) {
    const map = { done: '任务已完成', failed: '任务失败', stopped: '任务已停止' }
    return map[status] || ''
  }
  const list = steps || []
  const bootstrap = list.find(isBootstrapStep)
  const agentSteps = list.filter((s) => !isBootstrapStep(s))
  if (agentSteps.length > 0) {
    const last = agentSteps[agentSteps.length - 1]
    const label = browserLabStepLabel(last)
    const goal = (last.next_goal || last.thinking || '').trim()
    return goal ? `${label} · ${goal.slice(0, 120)}` : `${label} 执行中…`
  }
  if (bootstrap?.next_goal) return bootstrap.next_goal
  if (running) return 'Runner 正在启动浏览器并调度 Agent…'
  return ''
}
