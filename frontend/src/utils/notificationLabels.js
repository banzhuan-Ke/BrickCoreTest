/** 站内信 / 通知中心分类与事件中文文案 */

const CATEGORY_LABELS = {
  test_management: '测试管理',
  review: '评审',
  defect: '缺陷',
  assignment: '指派',
  release: '版本',
  system: '系统',
  other: '其他'
}

const EVENT_TYPE_LABELS = {
  defect_assigned: '缺陷指派',
  scope_owner_assigned: '范围负责人',
  review_invited: '评审邀请',
  review_item_pending: '评审待办',
  plan_run_item_assigned: '运行项指派',
  quality_gate_failed: '质量门禁'
}

export function notificationCategoryLabel(category) {
  const key = String(category || '').trim()
  if (!key) return '通知'
  return CATEGORY_LABELS[key] || key.replace(/_/g, ' ')
}

export function notificationEventTypeLabel(eventType) {
  const key = String(eventType || '').trim()
  if (!key) return ''
  return EVENT_TYPE_LABELS[key] || key
}
