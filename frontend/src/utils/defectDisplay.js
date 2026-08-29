/** 缺陷严重度 / 优先级 / 状态展示标签 */
export const DEFECT_STATUS_LABELS = {
  open: '打开',
  in_progress: '处理中',
  resolved: '已修复',
  verified: '已验证',
  closed: '已关闭',
  rejected: '已拒绝'
}

export const DEFECT_SEVERITY_LABELS = {
  blocker: '阻塞',
  critical: '严重',
  major: '一般',
  minor: '轻微'
}

export const DEFECT_STATUS_TAG_TYPE = {
  open: 'danger',
  in_progress: 'warning',
  resolved: 'success',
  verified: 'success',
  closed: 'info',
  rejected: 'info'
}

export const DEFECT_SEVERITY_TAG_TYPE = {
  blocker: 'danger',
  critical: 'danger',
  major: 'warning',
  minor: 'info'
}

export const DEFECT_PRIORITY_TAG_TYPE = {
  p0: 'danger',
  p1: 'warning',
  p2: '',
  p3: 'info'
}

/** 列表快捷流转：当前状态 → 下一状态 */
export const DEFECT_QUICK_TRANSITIONS = {
  open: { to: 'in_progress', label: '开始处理' },
  in_progress: { to: 'resolved', label: '标为已修复' },
  resolved: { to: 'verified', label: '验证通过' },
  verified: { to: 'closed', label: '关闭' },
  rejected: { to: 'open', label: '重新打开' },
  closed: { to: 'open', label: '重新打开' }
}

export function defectStatusLabel(s) {
  return DEFECT_STATUS_LABELS[s] || s || '—'
}

export function defectSeverityLabel(s) {
  return DEFECT_SEVERITY_LABELS[s] || s || '—'
}

/** 是否可对缺陷做流程流转（负责人/处理人；未指派时需 edit 权限认领） */
export function canUserProcessDefect(row, userInfo, { canView = false, canEdit = false } = {}) {
  if (!row || !canView) return false
  const uid = Number(userInfo?.id)
  if (!uid) return false
  if (userInfo?.is_superuser) return true
  const owners = [row.assignee_id, row.handler_id].filter((x) => x != null).map(Number)
  if (!owners.length) return !!canEdit
  return owners.includes(uid)
}

/** 新建缺陷描述默认模板（参考禅道） */
export const DEFECT_DESCRIPTION_TEMPLATE = `前置条件：

操作步骤：

实际结果：

预期结果：
`
