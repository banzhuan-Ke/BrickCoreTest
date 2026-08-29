/** 测试计划项类型展示 */
export const PLAN_ITEM_TYPE_LABELS = {
  functional_manual: '功能手工',
  ui_case: 'UI 用例',
  app_case: 'App 用例',
  api_case: '接口用例',
  perf_scene: '压测场景'
}

export const planItemTypeLabel = (t) => PLAN_ITEM_TYPE_LABELS[t] || t || '—'
