import { knowledgeApi } from '@/api/modules/knowledge.js'

/**
 * 轮询迭代报告/定制包生成状态，直到 ready / failed / 超时。
 * @returns {Promise<object>} 最终 report detail
 */
export async function pollIterationReportStatus(reportId, projectId, {
  maxAttempts = 120,
  intervalMs = 2000,
  onProgress = null
} = {}) {
  for (let i = 0; i < maxAttempts; i++) {
    const res = await knowledgeApi.getIterationReport(reportId, projectId)
    const data = res.data || {}
    if (typeof onProgress === 'function') {
      onProgress(data, i + 1)
    }
    if (data.status === 'ready') return data
    if (data.status === 'failed') {
      throw new Error(data.error || '报告生成失败')
    }
    await new Promise((r) => setTimeout(r, intervalMs))
  }
  throw new Error('生成超时，请稍后在「生成记录」查看状态')
}

/** 列表中是否存在进行中的报告 */
export function hasInFlightReports(reports) {
  return (reports || []).some((r) => r.status === 'generating' || r.status === 'pending')
}

/** 合并轮询结果到列表（按 id 更新） */
export function mergeReportRow(reports, updated) {
  if (!updated?.id) return reports
  const idx = reports.findIndex((r) => r.id === updated.id)
  if (idx >= 0) {
    const next = [...reports]
    next[idx] = { ...next[idx], ...updated }
    return next
  }
  return reports
}
