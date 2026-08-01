/**
 * 跳转到迭代报告向导并预填执行记录等参数。
 * @param {import('vue-router').Router} router
 * @param {{ reportType: string, recordId: number|string, reportKind?: string, folderId?: number, title?: string }} opts
 */
export function openIterationReportWizard(router, {
  reportType,
  recordId,
  reportKind = 'iteration_report',
  folderId,
  title
}) {
  const query = {
    report_kind: reportKind,
    exec: `${reportType}:${recordId}`
  }
  if (folderId != null) query.folder_id = String(folderId)
  if (title) query.title = title
  router.push({ path: '/ai-knowledge/reports', query })
}

/** 解析 query.exec 为 execKey 数组 */
export function parseExecQuery(raw) {
  if (!raw || typeof raw !== 'string') return []
  return raw.split(',').map((s) => s.trim()).filter(Boolean)
}
