/** 测试管理 · 状态/优先级等中文展示（统一口径） */

export const PLAN_RUN_STATUS_LABELS = {
  running: '运行中',
  completed: '已完成',
  cancelled: '已取消'
}

export const PLAN_STATUS_LABELS = {
  draft: '草稿',
  ready: '就绪',
  running: '运行中',
  completed: '已完成',
  cancelled: '已取消'
}

export const RUN_ITEM_RESULT_LABELS = {
  not_run: '未跑',
  passed: '通过',
  failed: '失败',
  blocked: '阻塞',
  skipped: '跳过',
  cancelled: '已取消',
  error: '错误',
  running: '执行中'
}

export const DEFECT_PRIORITY_LABELS = {
  p0: 'P0',
  p1: 'P1',
  p2: 'P2',
  p3: 'P3'
}

export const DEFECT_RESOLUTION_LABELS = {
  fixed: '已解决',
  not_repro: '无法重现',
  duplicate: '重复缺陷',
  by_design: '设计如此',
  external: '外部原因',
  will_not_fix: '不予解决',
  postponed: '延期处理',
  invalid: '无效问题'
}

export const DEFECT_RESOLUTION_OPTIONS = Object.entries(DEFECT_RESOLUTION_LABELS).map(([value, label]) => ({
  value,
  label
}))

export const REQUIREMENT_PARSE_STATUS_LABELS = {
  pending: '待解析',
  parsing: '解析中',
  parsed: '已解析',
  failed: '解析失败'
}

export const REQUIREMENT_REVIEW_STATUS_LABELS = {
  none: '未评审',
  pending: '待评审',
  in_review: '评审中',
  approved: '已通过',
  changes_requested: '需修改',
  rejected: '已驳回'
}

export function planRunStatusLabel(s) {
  return PLAN_RUN_STATUS_LABELS[s] || s || '—'
}

export function planStatusLabel(s) {
  return PLAN_STATUS_LABELS[s] || s || '—'
}

export function runItemResultLabel(s) {
  return RUN_ITEM_RESULT_LABELS[s] || s || '—'
}

export function defectPriorityLabel(p) {
  return DEFECT_PRIORITY_LABELS[String(p || '').toLowerCase()] || String(p || '—').toUpperCase()
}

export function defectResolutionLabel(t) {
  return DEFECT_RESOLUTION_LABELS[t] || t || '—'
}

export function requirementParseStatusLabel(s) {
  return REQUIREMENT_PARSE_STATUS_LABELS[s] || s || ''
}

export function requirementReviewStatusLabel(s) {
  return REQUIREMENT_REVIEW_STATUS_LABELS[s] || s || ''
}
