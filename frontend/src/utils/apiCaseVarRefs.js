/** 从接口用例表单中提取 ${{...}} 占位引用 */
import { classifyVarRef } from './caseVarRefs'

const PLACEHOLDER_PATTERN = /\$\{\{([^}]+)\}\}/g

function addRef(map, expr, fieldLabel) {
  const trimmed = (expr || '').trim()
  if (!trimmed) return
  if (!map.has(trimmed)) {
    const meta = classifyVarRef(trimmed)
    map.set(trimmed, {
      expr: trimmed,
      display: `\${{${trimmed}}}`,
      type: meta.type,
      typeLabel: meta.label,
      tagType: meta.tag,
      count: 0,
      steps: [],
    })
  }
  const row = map.get(trimmed)
  row.count += 1
  if (fieldLabel && !row.steps.includes(fieldLabel)) {
    row.steps.push(fieldLabel)
  }
}

function scanString(map, text, fieldLabel) {
  if (typeof text !== 'string' || !text.includes('${{')) return
  PLACEHOLDER_PATTERN.lastIndex = 0
  let match
  while ((match = PLACEHOLDER_PATTERN.exec(text)) !== null) {
    addRef(map, match[1], fieldLabel)
  }
}

function scanValue(map, value, fieldLabel) {
  if (value == null) return
  if (typeof value === 'string') {
    scanString(map, value, fieldLabel)
    return
  }
  if (Array.isArray(value)) {
    value.forEach((item, idx) => {
      if (item && typeof item === 'object') {
        scanString(map, item.key, fieldLabel)
        scanString(map, item.name, fieldLabel)
        scanValue(map, item.value, fieldLabel)
        scanValue(map, item.default, fieldLabel)
      } else {
        scanValue(map, item, fieldLabel)
      }
    })
    return
  }
  if (typeof value === 'object') {
    Object.entries(value).forEach(([k, v]) => {
      scanString(map, k, fieldLabel)
      scanValue(map, v, fieldLabel)
    })
  }
}

/** @param {object} caseForm 接口用例表单 */
export function extractApiCaseVarRefs(caseForm) {
  const map = new Map()
  if (!caseForm) return []

  scanValue(map, caseForm.request_headers, '请求头')
  scanValue(map, caseForm.request_params, '请求参数')
  scanValue(map, caseForm.request_body, '请求体')
  scanValue(map, caseForm.request_body_fields, 'form-data')
  scanValue(map, caseForm.assertions, '断言')
  scanValue(map, caseForm.assertion_groups, '条件断言')
  scanValue(map, caseForm.extractors, '变量提取')
  scanString(map, caseForm.pre_script, '前置脚本')
  scanString(map, caseForm.post_script, '后置脚本')
  scanValue(map, caseForm.data_set, '数据集')
  scanValue(map, caseForm.db_assertions, '库断言')
  scanValue(map, caseForm.ws_steps, 'WS步骤')

  return [...map.values()].sort((a, b) => {
    const typeOrder = { var: 0, df: 1, dt: 2, fragment: 3, csv: 4 }
    const ta = typeOrder[a.type] ?? 9
    const tb = typeOrder[b.type] ?? 9
    if (ta !== tb) return ta - tb
    return a.expr.localeCompare(b.expr, 'zh-CN')
  })
}
