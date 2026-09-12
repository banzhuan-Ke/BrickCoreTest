/**
 * 检测接口/用例内容中的 csv.* / @csv.* 引用（压测场景 CSV 参数化）。
 * CSV 仅在压测场景执行时自动注入；接口调试/单条执行默认不注入。
 */

const PLACEHOLDER_CSV = /\$\{\{\s*csv\.([^}|]+)/gi
const LEGACY_CSV = /\{\{\s*csv\.([^}|]+)/gi
const AT_CSV = /@csv\.([a-zA-Z_][\w]*)/g

function addName(set, name) {
  const n = String(name || '').trim()
  if (n) set.add(n)
}

function scanString(set, text) {
  if (typeof text !== 'string' || !text) return
  if (!text.includes('csv.') && !text.includes('@csv.')) return
  PLACEHOLDER_CSV.lastIndex = 0
  LEGACY_CSV.lastIndex = 0
  AT_CSV.lastIndex = 0
  let m
  while ((m = PLACEHOLDER_CSV.exec(text)) !== null) addName(set, m[1])
  while ((m = LEGACY_CSV.exec(text)) !== null) addName(set, m[1])
  while ((m = AT_CSV.exec(text)) !== null) addName(set, m[1])
}

function scanValue(set, value) {
  if (value == null) return
  if (typeof value === 'string') {
    scanString(set, value)
    return
  }
  if (Array.isArray(value)) {
    value.forEach((item) => scanValue(set, item))
    return
  }
  if (typeof value === 'object') {
    Object.values(value).forEach((item) => scanValue(set, item))
  }
}

/** @returns {string[]} 去重后的列名 */
export function listCsvColumnRefs(source) {
  const set = new Set()
  scanValue(set, source)
  return [...set].sort((a, b) => a.localeCompare(b, 'zh-CN'))
}

export function hasCsvRefs(source) {
  return listCsvColumnRefs(source).length > 0
}

/** 调试页请求对象扫描 */
export function listCsvRefsFromDebugRequest(request, bodyText = '') {
  return listCsvColumnRefs({
    url: request?.url,
    headers: request?.headers,
    params: request?.params,
    body: request?.body,
    body_fields: request?.body_fields,
    bodyText,
  })
}
