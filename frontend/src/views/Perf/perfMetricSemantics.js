/**
 * 压测报告指标语义：好坏方向、中文名、文案内百分比着色。
 * 与 backend perf_html_theme.metric_lower_is_better / pct_tone 对齐。
 */

const HIGHER_BETTER = new Set([
  'qps',
  'success_qps',
  'avg_qps',
  'total_requests',
  'success_count',
])

const LOWER_BETTER = new Set([
  'avg_response_time',
  'avg_rt',
  'p95_response_time',
  'p95',
  'p95_rt',
  'avg_p95',
  'p90_response_time',
  'p99_response_time',
  'error_rate',
  'avg_error_rate',
  'max_response_time',
  'duration',
  'avg_duration',
])

const BASE_LABELS = {
  qps: 'QPS',
  success_qps: '成功 QPS',
  avg_qps: '平均 QPS',
  avg_response_time: '平均响应时间',
  avg_rt: '平均响应时间',
  p95_response_time: 'P95',
  p95: 'P95',
  p95_rt: 'P95',
  error_rate: '错误率',
  total_requests: '总请求数',
  success_count: '成功请求数',
  total_time: '整体耗时',
  answer_duration: '回答耗时',
  answer_start: '回答开始',
  retrieval_duration: '检索耗时',
  retrieval_start: '检索开始',
  retrieval_end: '检索结束',
}

const KEY_ALIASES = {
  avg_rt: 'avg_response_time',
  p95: 'p95_response_time',
  avg_response_time: 'avg_rt',
  p95_response_time: 'p95',
}

/** 与导出 HTML「附录：指标说明」对齐 */
export const METRIC_GLOSSARY_ROWS = [
  { name: 'QPS', meaning: '每秒完成的请求数（Queries Per Second）。HTTP 场景下可近似理解为 TPS。' },
  { name: '成功 QPS', meaning: '仅统计成功请求的每秒吞吐，不含失败请求。' },
  { name: '平均 RT / Avg', meaning: '全部（或标注范围内）请求的平均响应时间，单位毫秒。' },
  { name: 'P50 / Median', meaning: '中位数响应时间：50% 的请求不高于该值。' },
  { name: 'P90', meaning: '90% 的请求响应时间不高于该值。' },
  { name: 'P95', meaning: '95% 的请求响应时间不高于该值，常用来衡量大多数用户体验与长尾。' },
  { name: 'P99', meaning: '99% 的请求响应时间不高于该值，更敏感地反映极端慢请求。' },
  { name: 'Min / Max RT', meaning: '本次统计窗口内最短 / 最长响应时间。' },
  { name: '错误率', meaning: '失败请求数 ÷ 总请求数 × 100%。失败含 HTTP 异常或断言未通过。' },
  { name: '总请求 / 成功 / 失败', meaning: '压测期间发出的请求总数，以及成功、失败次数。' },
  { name: '并发用户数', meaning: '压测配置的虚拟用户（VU）数量。' },
  { name: 'Ramp-up', meaning: '从 0 爬升到目标并发所需秒数，用于缓和加压。' },
  { name: '预热', meaning: '正式计时前的预热秒数，预热期间的请求通常不计入正式指标。' },
  { name: '实际时长', meaning: '压测从开始到结束的墙钟耗时（秒）。' },
  { name: '阶段耗时（整体/回答/检索等）', meaning: '流式或链路场景下各阶段耗时均值/P95，单位秒；越低通常越好。' },
  { name: '参照轮 / 对比轮', meaning: '参照轮是计算变化率时的参照对象；对比轮相对它计算百分比。同名场景请结合执行时间 / 记录号区分。' },
  { name: '变化率', meaning: '（对比轮 − 参照轮）÷ 参照轮 × 100%。QPS/请求数升高通常更好；RT/错误率/阶段耗时升高通常更差。' },
  { name: '共有 / 独有接口', meaning: '按接口名称对齐：各轮都有的为共有；仅某轮出现的为独有（缺侧显示「本轮无」）。' },
  { name: '趋势图 QPS 柱', meaning: '该秒瞬时完成请求数，不是全程平均 QPS。' },
  { name: '趋势图 RT 折线', meaning: '该秒有完成请求时的平均 / P95 响应时间；空闲秒不标点，折线连续跨过。' },
  { name: '响应时间分布', meaning: '按耗时区间统计请求个数，用于观察延迟是否集中、是否存在长尾。' },
]

export function escapeHtml(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

/** True=越低越好；False=越高越好；null=中性 */
export function metricLowerIsBetter(metricKey) {
  const k = String(metricKey || '').toLowerCase()
  if (!k) return null
  if (HIGHER_BETTER.has(k)) return false
  if (LOWER_BETTER.has(k)) return true
  if (k.startsWith('phase_')) return true
  return null
}

export function pctTone(key, pct, lowerIsBetter) {
  if (pct === undefined || pct === null || Number.isNaN(Number(pct))) return 'flat'
  const n = Number(pct)
  if (Math.abs(n) < 0.5) return 'flat'
  let lib = lowerIsBetter
  if (lib === undefined) lib = metricLowerIsBetter(key)
  if (lib == null) return 'flat'
  const up = n > 0
  const better = lib ? !up : up
  return better ? 'better' : 'worse'
}

export function pctColor(key, pct, lowerIsBetter) {
  const tone = pctTone(key, pct, lowerIsBetter)
  if (tone === 'better') return '#15803d'
  if (tone === 'worse') return '#b91c1c'
  return '#64748b'
}

export function pctClass(key, pct, lowerIsBetter) {
  const tone = pctTone(key, pct, lowerIsBetter)
  if (tone === 'better') return 'pct-better'
  if (tone === 'worse') return 'pct-worse'
  return 'pct-flat'
}

export function buildMetricLabelMap(metricRows = []) {
  const out = { ...BASE_LABELS }
  for (const m of metricRows || []) {
    if (!m || typeof m !== 'object') continue
    const key = String(m.key || '').trim()
    const label = String(m.label || '').trim()
    if (key && label) {
      out[key] = label
      if (m.phase_key) {
        const pk = String(m.phase_key)
        const head = label.split(/\s+/)[0] || pk
        out[pk] = out[pk] || head
      }
    }
  }
  return out
}

export function humanizeMetricKey(key, labelMap = {}) {
  const k = String(key || '').trim()
  if (!k) return ''
  if (labelMap[k]) return labelMap[k]
  if (BASE_LABELS[k]) return BASE_LABELS[k]
  const alias = KEY_ALIASES[k]
  if (alias && labelMap[alias]) return labelMap[alias]

  const m = k.match(/^phase_(mean|p95|min|max|median)_(.+)$/i)
  if (m) {
    if (labelMap[k]) return labelMap[k]
    const stat = { mean: '均值', p95: 'P95', min: '最小', max: '最大', median: '中位' }[m[1].toLowerCase()] || m[1]
    const phaseKey = m[2]
    const meanKey = `phase_mean_${phaseKey}`
    if (m[1].toLowerCase() !== 'mean' && labelMap[meanKey]) {
      const baseLab = String(labelMap[meanKey]).replace(/\s*均值.*$/, '').trim()
      if (baseLab) return `${baseLab} ${stat}`
    }
    const base = labelMap[phaseKey] || BASE_LABELS[phaseKey] || phaseKey.replace(/_/g, ' ')
    return `${base}${stat}`
  }
  if (/^[a-z][a-z0-9_]*$/i.test(k) && k.includes('_')) {
    return k.replace(/_/g, ' ')
  }
  return k
}

/**
 * 将文案中的「下降73% / +12% / 增加 181.08%」等按指标好坏着色。
 * 返回可安全 v-html 的字符串。
 */
export function colorizePctPhrases(text, { metricKey, lowerIsBetter } = {}) {
  if (text == null || text === '') return ''
  const lib =
    lowerIsBetter !== undefined && lowerIsBetter !== null
      ? lowerIsBetter
      : metricLowerIsBetter(metricKey)
  const escaped = escapeHtml(text)
  const re = /(上升|下降|增加|减少|升高|降低|改善|恶化)?\s*([+-]?\d+(?:\.\d+)?)\s*%/g
  return escaped.replace(re, (full, verb, numStr) => {
    const n = Number(numStr)
    if (!Number.isFinite(n)) return full
    if (verb === '改善') return `<span class="pct-better">${full}</span>`
    if (verb === '恶化') return `<span class="pct-worse">${full}</span>`
    let up = n > 0
    if (verb && /下降|减少|降低/.test(verb)) up = false
    if (verb && /上升|增加|升高/.test(verb)) up = true
    if (Math.abs(n) < 0.5) return `<span class="pct-flat">${full}</span>`
    if (lib == null) {
      // 无指标方向时：带「下降/增加」的百分比仍加粗灰显，避免误导成好坏
      return `<span class="pct-emphasis">${full}</span>`
    }
    const better = lib ? !up : up
    return `<span class="${better ? 'pct-better' : 'pct-worse'}">${full}</span>`
  })
}

export function noteToneFromText(text, metricKey) {
  const html = colorizePctPhrases(text, { metricKey })
  if (html.includes('pct-worse')) return 'warn'
  if (html.includes('pct-better')) return 'success'
  return 'info'
}
