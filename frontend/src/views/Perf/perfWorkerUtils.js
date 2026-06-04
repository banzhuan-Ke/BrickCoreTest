/** 解析 Worker 列表 API 响应（后端直接返回数组） */
export function parseWorkerList(res) {
  const raw = res?.data ?? res
  return Array.isArray(raw) ? raw : (raw?.data ?? [])
}

/** 在线执行机：非 offline 状态 */
export function filterOnlineWorkers(list) {
  return (list || []).filter(w => w.status && w.status !== 'offline')
}
