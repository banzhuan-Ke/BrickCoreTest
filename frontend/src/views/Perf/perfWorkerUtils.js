/** 解析 Worker 列表 API 响应（后端直接返回数组） */
export function parseWorkerList(res) {
  const raw = res?.data ?? res
  return Array.isArray(raw) ? raw : (raw?.data ?? [])
}

/** 在线执行机：非 offline 状态 */
export function filterOnlineWorkers(list) {
  return (list || []).filter(w => w.status && w.status !== 'offline')
}

/**
 * 按权重预览分压（与后端 distribute_by_weights 对齐）。
 * @param {number} total 总并发
 * @param {number[]} capacities 各机 max_concurrent
 * @param {number[]} [weights] 权重；缺省用 capacities
 * @returns {number[]}
 */
export function distributeByWeights(total, capacities, weights) {
  const n = (capacities || []).length
  if (!n) return []
  const caps = capacities.map((c) => Math.max(0, Number(c) || 0))
  if (caps.reduce((a, b) => a + b, 0) <= 0) return caps.map(() => 0)

  let wts
  if (!weights || weights.length !== n) {
    wts = caps.map((c) => (c > 0 ? Math.max(1, c) : 0))
  } else {
    wts = weights.map((w, i) => {
      const v = Math.max(0, Number(w) || 0)
      if (caps[i] > 0 && v <= 0) return 1
      return v
    })
  }
  const totalWeight = wts.reduce((a, b) => a + b, 0)
  if (totalWeight <= 0) return caps.map(() => 0)

  let remaining = Math.max(0, Math.floor(Number(total) || 0))
  const totalNum = Math.max(0, Math.floor(Number(total) || 0))
  const assignments = []
  for (let i = 0; i < n; i++) {
    if (caps[i] <= 0 || wts[i] <= 0) {
      assignments.push(0)
      continue
    }
    let assigned = Math.floor((totalNum * wts[i]) / totalWeight)
    assigned = Math.min(assigned, caps[i])
    if (remaining > 0 && assigned === 0) assigned = 1
    assigned = Math.min(assigned, remaining, caps[i])
    assignments.push(assigned)
    remaining -= assigned
  }
  let idx = 0
  let guard = 0
  while (remaining > 0 && guard <= n * 10) {
    const i = idx % n
    if (assignments[i] < caps[i]) {
      assignments[i] += 1
      remaining -= 1
    }
    idx += 1
    guard += 1
  }
  return assignments
}

/** 场景需要的峰值并发（stepping 取阶段峰值） */
export function neededConcurrentFromConfig(config) {
  const cfg = config || {}
  if (cfg.mode === 'stepping') {
    const steps = cfg.steps || []
    if (!steps.length) return 1
    return Math.max(...steps.map((s) => Number(s.users) || 1), 1)
  }
  return Math.max(1, Number(cfg.concurrent_users) || 1)
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
