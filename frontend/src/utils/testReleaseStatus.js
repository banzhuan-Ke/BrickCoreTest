/** 与 backend app/modules/test_management/rules.py 状态机对齐 */

export const RELEASE_STATUS_LABELS = {
  draft: '草稿',
  testing: '测试中',
  ready: '就绪',
  released: '已发布',
  archived: '已归档'
}

export const RELEASE_TRANSITIONS = {
  draft: ['testing', 'archived'],
  testing: ['ready', 'archived'],
  ready: ['testing', 'released', 'archived'],
  released: ['archived'],
  archived: []
}

export function releaseStatusLabel(status) {
  return RELEASE_STATUS_LABELS[status] || status || '—'
}

export function allowedReleaseTransitions(status) {
  return RELEASE_TRANSITIONS[status] || []
}

export function primaryReleaseTransition(status) {
  const map = {
    draft: 'testing',
    testing: 'ready',
    ready: 'released',
    released: 'archived'
  }
  return map[status] || null
}

export function releaseScopeEditable(status) {
  return ['draft', 'testing', 'ready'].includes(status)
}

export function releaseDeletable(status) {
  return status !== 'released' && status !== 'archived'
}

export const QUALITY_STATUS_LABELS = {
  pass: '通过',
  conditional_pass: '有条件通过',
  failed: '未通过',
  blocked: '阻塞'
}

export function qualityStatusLabel(status) {
  return QUALITY_STATUS_LABELS[status] || status || '—'
}

export function qualityStatusTagType(status) {
  const map = {
    pass: 'success',
    conditional_pass: 'warning',
    failed: 'danger',
    blocked: 'danger'
  }
  return map[status] || 'info'
}
