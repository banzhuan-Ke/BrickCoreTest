/** 从 UI 用例步骤 JSON 中提取 ${{...}} 占位引用 */

const PLACEHOLDER_PATTERN = /\$\{\{([^}]+)\}\}/g
const AT_VAR_IN_DT = /@([a-zA-Z_][\w.]*)/

const TYPE_META = {
  var: { label: '变量', tag: 'primary' },
  df: { label: '数据工厂', tag: 'success' },
  dt: { label: '内联工具', tag: 'warning' },
  fragment: { label: '片段入参', tag: 'info' },
  csv: { label: 'CSV', tag: '' },
}

export function classifyVarRef(rawExpr) {
  const expr = (rawExpr || '').trim()
  if (!expr) return { type: 'var', label: TYPE_META.var.label, tag: TYPE_META.var.tag, name: expr, expr }
  if (expr.startsWith('df:')) {
    return { type: 'df', label: TYPE_META.df.label, tag: TYPE_META.df.tag, name: expr.slice(3), expr }
  }
  if (expr.startsWith('dt:')) {
    return { type: 'dt', label: TYPE_META.dt.label, tag: TYPE_META.dt.tag, name: expr, expr }
  }
  if (expr.startsWith('fragment.')) {
    return { type: 'fragment', label: TYPE_META.fragment.label, tag: TYPE_META.fragment.tag, name: expr.slice(9), expr }
  }
  if (expr.startsWith('csv.')) {
    return { type: 'csv', label: TYPE_META.csv.label, tag: TYPE_META.csv.tag, name: expr.slice(4), expr }
  }
  return { type: 'var', label: TYPE_META.var.label, tag: TYPE_META.var.tag, name: expr, expr }
}

function addRef(map, expr, stepNo) {
  const trimmed = (expr || '').trim()
  if (!trimmed) return
  const key = trimmed
  if (!map.has(key)) {
    const meta = classifyVarRef(trimmed)
    map.set(key, {
      expr: trimmed,
      display: `\${{${trimmed}}}`,
      type: meta.type,
      typeLabel: meta.label,
      tagType: meta.tag,
      count: 0,
      steps: [],
    })
  }
  const row = map.get(key)
  row.count += 1
  if (stepNo && !row.steps.includes(stepNo)) {
    row.steps.push(stepNo)
  }
}

function scanString(map, text, stepNo) {
  if (typeof text !== 'string' || !text.includes('${{')) return
  PLACEHOLDER_PATTERN.lastIndex = 0
  let match
  while ((match = PLACEHOLDER_PATTERN.exec(text)) !== null) {
    const inner = (match[1] || '').trim()
    addRef(map, inner, stepNo)
    if (inner.startsWith('dt:')) {
      const atMatch = AT_VAR_IN_DT.exec(inner)
      if (atMatch?.[1]) addRef(map, atMatch[1], stepNo)
    }
  }
}

function scanValue(map, value, stepNo) {
  if (value == null) return
  if (typeof value === 'string') {
    scanString(map, value, stepNo)
    return
  }
  if (Array.isArray(value)) {
    value.forEach((item) => scanValue(map, item, stepNo))
    return
  }
  if (typeof value === 'object') {
    Object.values(value).forEach((item) => scanValue(map, item, stepNo))
  }
}

function walkSteps(steps, map, pathPrefix = '') {
  if (!Array.isArray(steps)) return
  steps.forEach((step, index) => {
    if (!step || typeof step !== 'object') return
    const stepNo = pathPrefix ? `${pathPrefix}.${index + 1}` : String(index + 1)
    scanValue(map, step.params, stepNo)
    scanValue(map, step.desc, stepNo)
    if (step.method === 'condition_branch' && Array.isArray(step.branches)) {
      step.branches.forEach((branch, bIndex) => {
        walkSteps(branch?.steps, map, `${stepNo}·分支${bIndex + 1}`)
      })
    }
  })
}

/** @returns {Array<{ expr, display, type, typeLabel, tagType, count, steps }>} */
export function extractCaseVarRefs(steps) {
  const map = new Map()
  walkSteps(steps, map)
  return [...map.values()].sort((a, b) => {
    const typeOrder = { var: 0, df: 1, dt: 2, fragment: 3, csv: 4 }
    const ta = typeOrder[a.type] ?? 9
    const tb = typeOrder[b.type] ?? 9
    if (ta !== tb) return ta - tb
    return a.expr.localeCompare(b.expr, 'zh-CN')
  })
}
