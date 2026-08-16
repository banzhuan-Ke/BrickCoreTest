/** UI 步骤失败码展示（与 Runner failure_code 对齐） */

export const UI_FAILURE_CODE_LABELS = {
  BUSY_TIMEOUT: '忙碌遮罩超时',
  READY_TIMEOUT: '就绪等待超时',
  ACTION_TIMEOUT: '动作超时',
  INVALID_BUSY_SELECTOR: '忙碌选择器非法',
  INVALID_READY_SELECTOR: '就绪选择器非法',
  CANCELLED: '已取消',
  AMBIGUOUS_TARGET: '智能点击目标歧义',
  NO_ACTIONABLE_CANDIDATE: '无可用候选元素',
  ACTION_FAILED: '动作执行失败',
  POSTCONDITION_FAILED: '后置条件失败',
  MISSING_SAFETY_FIELDS: '缺少安全字段（区域/后置）',
}

export function formatFailureCode(code) {
  const c = String(code || '').trim()
  if (!c) return ''
  const label = UI_FAILURE_CODE_LABELS[c]
  return label ? `${label}（${c}）` : c
}

export function failureCodeTagType(code) {
  const c = String(code || '').trim().toUpperCase()
  if (c === 'CANCELLED') return 'info'
  if (c.startsWith('INVALID_')) return 'warning'
  if (c.endsWith('_TIMEOUT')) return 'danger'
  return 'danger'
}
