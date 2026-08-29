/** 性能验收目标 perf_targets（与后端 normalize / GLOBAL_METRIC_META 对齐） */

export const PERF_TARGET_GLOBAL_OPTIONS = [
  { key: 'qps', label: 'QPS', op: '>=', unit: '/s' },
  { key: 'success_qps', label: '成功 QPS', op: '>=', unit: '/s' },
  { key: 'total_requests', label: '总请求数', op: '>=', unit: '次' },
  { key: 'avg_response_time', label: '平均响应时间', op: '<=', unit: 'ms' },
  { key: 'success_avg_response_time', label: '成功平均响应时间', op: '<=', unit: 'ms' },
  { key: 'p90_response_time', label: 'P90 响应时间', op: '<=', unit: 'ms' },
  { key: 'p95_response_time', label: 'P95 响应时间', op: '<=', unit: 'ms' },
  { key: 'success_p95_response_time', label: '成功 P95 响应时间', op: '<=', unit: 'ms' },
  { key: 'p99_response_time', label: 'P99 响应时间', op: '<=', unit: 'ms' },
  { key: 'error_rate', label: '错误率', op: '<=', unit: '%' },
]

const DEFAULT_ENABLED_KEYS = new Set(['qps', 'p95_response_time', 'error_rate'])

function parseNonNegInt(val, fallback) {
  if (val === null || val === undefined || val === '') return fallback
  const n = parseInt(val, 10)
  if (!Number.isFinite(n) || n < 0) return fallback
  return n
}

function parseNonNegNumber(val) {
  if (val === '' || val === undefined || val === null) return null
  const n = Number(val)
  if (!Number.isFinite(n) || n < 0) return null
  return n
}

function globalItemSkeleton(meta, { enabled } = {}) {
  return {
    scope: 'global',
    key: meta.key,
    label: meta.label,
    op: meta.op,
    value: null,
    unit: meta.unit,
    severity: 'fail',
    enabled: enabled != null ? !!enabled : DEFAULT_ENABLED_KEYS.has(meta.key),
  }
}

function mergeGlobalItems(items) {
  const byKey = {}
  const others = []
  for (const it of items) {
    if (!it || typeof it !== 'object') continue
    if (it.scope === 'global' && PERF_TARGET_GLOBAL_OPTIONS.some((m) => m.key === it.key)) {
      byKey[it.key] = it
    } else {
      others.push(it)
    }
  }
  const merged = PERF_TARGET_GLOBAL_OPTIONS.map((m) =>
    byKey[m.key] ? byKey[m.key] : globalItemSkeleton(m, { enabled: false }),
  )
  return merged.concat(others)
}

export function defaultPerfTargets() {
  return {
    enabled: false,
    profile: 'custom',
    mode: 'all',
    min_total_requests: 100,
    min_duration_seconds: 60,
    items: PERF_TARGET_GLOBAL_OPTIONS.map((m) => globalItemSkeleton(m)),
  }
}

export function normalizePerfTargetsLocal(raw) {
  const base = defaultPerfTargets()
  if (!raw || typeof raw !== 'object') return base
  const meta = Object.fromEntries(PERF_TARGET_GLOBAL_OPTIONS.map((m) => [m.key, m]))
  const itemsIn = Array.isArray(raw.items) ? raw.items : []
  const items = []
  for (const it of itemsIn) {
    if (!it || it.scope === 'case' || it.scope === 'phase') {
      // 第一版 UI 只编辑 global；保留非 global 项以免保存冲掉
      if (it && (it.scope === 'case' || it.scope === 'phase')) {
        items.push({ ...it })
      }
      continue
    }
    const key = String(it.key || '')
    const m = meta[key]
    if (!m) continue
    items.push({
      scope: 'global',
      key,
      label: it.label || m.label,
      op: it.op || m.op,
      value: parseNonNegNumber(it.value),
      unit: it.unit || m.unit,
      severity: it.severity === 'warn' ? 'warn' : 'fail',
      enabled: it.enabled !== false,
    })
  }
  const globalItems = items.filter((i) => i.scope === 'global')
  const otherItems = items.filter((i) => i.scope !== 'global')
  const filled = mergeGlobalItems(globalItems.length ? globalItems : base.items)
  return {
    enabled: !!raw.enabled,
    profile: 'custom',
    mode: 'all',
    // 允许 0（关闭可信度门槛）；不可用 ||，否则 0 会被改回默认
    min_total_requests: parseNonNegInt(raw.min_total_requests, 100),
    min_duration_seconds: parseNonNegInt(raw.min_duration_seconds, 60),
    items: filled.filter((i) => i.scope === 'global').concat(otherItems),
  }
}

/**
 * 就地补齐全局指标行（旧场景 config 往往只有 QPS/P95/错误率三项）。
 */
export function ensureGlobalTargetItems(targets) {
  if (!targets || typeof targets !== 'object') return targets
  const next = normalizePerfTargetsLocal(targets)
  const curGlobals = (targets.items || []).filter((i) => i && i.scope === 'global')
  if (curGlobals.length >= PERF_TARGET_GLOBAL_OPTIONS.length) {
    const keySet = new Set(curGlobals.map((i) => i.key))
    if (PERF_TARGET_GLOBAL_OPTIONS.every((m) => keySet.has(m.key))) {
      return targets
    }
  }
  targets.enabled = next.enabled
  targets.profile = next.profile
  targets.mode = next.mode
  targets.min_total_requests = next.min_total_requests
  targets.min_duration_seconds = next.min_duration_seconds
  targets.items = next.items
  return targets
}

export function perfTargetsSummaryLines(targets) {
  const t = normalizePerfTargetsLocal(targets)
  if (!t.enabled) return ['未启用性能验收目标']
  const lines = []
  for (const it of t.items) {
    if (it.scope !== 'global' || !it.enabled || it.value == null || it.value === '') continue
    lines.push(`${it.label} ${it.op} ${it.value}${it.unit ? ' ' + it.unit : ''}（${it.severity === 'warn' ? '警告' : '失败'}）`)
  }
  if (!lines.length) return ['已启用，但尚未填写有效目标值']
  return lines
}
