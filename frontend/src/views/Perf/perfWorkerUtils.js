/** 解析 Worker 列表 API 响应（后端直接返回数组） */
export function parseWorkerList(res) {
  const raw = res?.data ?? res
  return Array.isArray(raw) ? raw : (raw?.data ?? [])
}

/** 在线执行机：非 offline 状态 */
export function filterOnlineWorkers(list) {
  return (list || []).filter(w => w.status && w.status !== 'offline')
}

/** agent_kind → 展示文案（空=旧客户端，按计划视为完整 Runner 兼容） */
export function agentKindLabel(kind) {
  const k = (kind || '').trim()
  if (k === 'perf_slim') return '精简包'
  if (k === 'runner_client') return '完整客户端'
  if (!k) return '完整客户端'
  return k
}

export function agentKindTagType(kind) {
  const k = (kind || '').trim()
  if (k === 'perf_slim') return 'warning'
  if (k === 'runner_client') return 'success'
  return 'info'
}

export function agentKindShort(kind) {
  const k = (kind || '').trim()
  if (k === 'perf_slim') return '精简包'
  if (k === 'runner_client') return '完整客户端'
  if (!k) return '兼容'
  return k
}
