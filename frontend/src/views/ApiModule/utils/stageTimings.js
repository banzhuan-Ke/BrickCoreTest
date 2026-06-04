const STAGE_LABEL_MAP = {
  load_case_ms: '加载用例/环境',
  merge_vars_ms: '变量合并',
  pre_script_ms: '前置脚本',
  build_request_ms: '构建请求',
  request_ms: 'HTTP 请求',
  assertion_ms: '断言执行',
  schema_validate_ms: 'Schema 校验',
  extract_vars_ms: '变量提取',
  post_script_ms: '后置脚本',
  db_assertion_ms: '库断言',
  total_ms: '总耗时'
}

const STAGE_COLOR_MAP = {
  load_case_ms: '#909399',
  merge_vars_ms: '#909399',
  pre_script_ms: '#e6a23c',
  build_request_ms: '#909399',
  request_ms: '#67c23a',
  assertion_ms: '#409eff',
  schema_validate_ms: '#409eff',
  extract_vars_ms: '#409eff',
  post_script_ms: '#e6a23c',
  db_assertion_ms: '#909399',
  total_ms: '#409eff'
}

export function formatStageTimings(timings) {
  if (!timings || typeof timings !== 'object') return []
  const total = timings.total_ms || 1
  const entries = Object.entries(timings).filter(([key, value]) => key !== 'total_ms' && value > 0)
  const rows = entries
    .map(([key, value]) => ({
      name: STAGE_LABEL_MAP[key] || key,
      value: Number(value).toFixed(1),
      percentage: Math.min(100, Math.round((value / total) * 100)),
      color: STAGE_COLOR_MAP[key] || '#409eff',
      isTotal: false
    }))
    .sort((a, b) => Number(b.value) - Number(a.value))

  rows.push({
    name: '总耗时',
    value: Number(total).toFixed(1),
    percentage: 100,
    color: '#409eff',
    isTotal: true
  })
  return rows
}
