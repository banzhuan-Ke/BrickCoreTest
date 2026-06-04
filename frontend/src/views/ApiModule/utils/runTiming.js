/**
 * 从执行结果中解析耗时（兼容历史数据：无 http_response_time 时从 stage_timings 读取）
 */
export function getHttpResponseMs(result) {
  if (!result) return null
  if (result.http_response_time != null) return Number(result.http_response_time)
  const rd = result.response_detail
  if (rd?.http_time != null) return Number(rd.http_time)
  const ms = result.request_detail?.stage_timings?.request_ms
  return ms != null ? Number(ms) : null
}

export function getCaseTotalMs(result) {
  if (!result) return null
  if (result.response_time != null) return Number(result.response_time)
  const rd = result.response_detail
  if (rd?.total_time != null) return Number(rd.total_time)
  const ms = result.request_detail?.stage_timings?.total_ms
  return ms != null ? Number(ms) : null
}

export function formatTimingMs(ms, digits = 2) {
  if (ms == null || Number.isNaN(ms)) return '-'
  return `${Number(ms).toFixed(digits)} ms`
}

/** 汇总多条用例的接口耗时 */
export function sumHttpResponseMs(caseResults) {
  if (!caseResults?.length) return null
  let sum = 0
  let has = false
  for (const item of caseResults) {
    const t = getHttpResponseMs(item)
    if (t != null) {
      sum += t
      has = true
    }
  }
  return has ? sum : null
}

/** 汇总计划 item_results 中所有用例的接口耗时 */
export function sumHttpFromPlanItems(planItems) {
  if (!planItems?.length) return null
  let sum = 0
  let has = false
  for (const planItem of planItems) {
    for (const c of planItem.case_results || []) {
      const t = getHttpResponseMs(c)
      if (t != null) {
        sum += t
        has = true
      }
    }
  }
  return has ? sum : null
}
