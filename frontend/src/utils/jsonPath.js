/**
 * JSONPath 轻量求值与路径转换（供断言/提取点选工具）。
 * 覆盖 $.a.b、$.a[0]、$.a[*]、data.type（无 $ 前缀）。
 * 过滤表达式 / 递归查找请到数据工厂「JSONPath 查询」用 jsonpath-ng。
 */

import { formatResponseExample, parseResponseExampleAsJson } from './responseExample.js'

const DEFAULT_SAMPLE = `{
  "code": 0,
  "message": "ok",
  "data": {
    "id": 1,
    "token": "demo-token"
  }
}`

const JSON_CACHE_KEY = 'brickcore.jsonpath.picker.json'
const JSON_CACHE_MAX = 200000

export function defaultJsonPathSample() {
  return DEFAULT_SAMPLE
}

/** 接口响应示例 → 弹窗预填 JSON；没有合法示例时返回空串 */
export function sampleJsonTextFromApi(api) {
  if (!api) return ''
  let schema = api.response_schema
  if (!schema) return ''
  if (typeof schema === 'string') {
    try {
      schema = JSON.parse(schema)
    } catch {
      return ''
    }
  }
  if (typeof schema !== 'object' || schema == null) return ''
  const example = schema.example
  if (example == null || example === '') return ''
  const formatted = formatResponseExample(example)
  const obj = parseResponseExampleAsJson(formatted)
  if (obj != null) {
    try {
      return JSON.stringify(obj, null, 2)
    } catch {
      return formatted
    }
  }
  const parsed = parseJsonSample(formatted)
  return parsed.ok ? JSON.stringify(parsed.value, null, 2) : ''
}

export function readCachedJsonSample() {
  try {
    return sessionStorage.getItem(JSON_CACHE_KEY) || ''
  } catch {
    return ''
  }
}

export function writeCachedJsonSample(text) {
  const raw = String(text || '')
  if (!raw || raw.length > JSON_CACHE_MAX) return
  try {
    sessionStorage.setItem(JSON_CACHE_KEY, raw)
  } catch {
    /* ignore quota / private mode */
  }
}

export function parseJsonSample(text) {
  const trimmed = (text ?? '').trim()
  if (!trimmed) return { ok: false, error: '请粘贴 JSON', value: null }
  try {
    return { ok: true, error: '', value: JSON.parse(trimmed) }
  } catch (e) {
    return { ok: false, error: `JSON 无法解析：${e.message || ''}`, value: null }
  }
}

/** vue-json-pretty 节点 path（root.a[0] / $.a[0]）→ $.a[0].b */
export function prettyPathToJsonPath(prettyPath, { unpackArrays = false } = {}) {
  if (prettyPath == null || prettyPath === '') return '$'
  let p = Array.isArray(prettyPath) ? prettyPath.join('.') : String(prettyPath)
  if (p === 'root' || p === '$') return '$'
  if (p.startsWith('root.')) p = `$.${p.slice(5)}`
  else if (p.startsWith('root[')) p = `$${p.slice(4)}`
  else if (!p.startsWith('$')) p = p.startsWith('.') ? `$${p}` : `$.${p}`
  return unpackArrays ? applyArrayUnpack(p) : p
}

export function applyArrayUnpack(path) {
  return String(path || '').replace(/\[(\d+)\]/g, '[*]')
}

export function evalJsonPath(root, path) {
  const raw = String(path || '').trim()
  if (!raw) return { ok: false, matched: false, error: '请填写 JSONPath', matches: [] }
  const tokens = tokenizeJsonPath(raw)
  if (tokens.error) return { ok: false, matched: false, error: tokens.error, matches: [] }
  try {
    const matches = walk(root, tokens.list, 0)
    return { ok: true, matched: matches.length > 0, error: '', matches }
  } catch (e) {
    return { ok: false, matched: false, error: e.message || 'JSONPath 无效', matches: [] }
  }
}

function tokenizeJsonPath(path) {
  let p = path.trim()
  if (p === '$') return { list: [], error: '' }
  if (p.startsWith('$.')) p = p.slice(2)
  else if (p.startsWith('$')) p = p.slice(1)
  const list = []
  const re = /\s*(?:([A-Za-z_][\w]*)|\[(\d+)\]|\[\*\]|\['([^']*)'\]|\["([^"]*)"\]|\.(\*))\.?/g
  let last = 0
  let m
  while ((m = re.exec(p))) {
    if (m.index !== last) return { list: [], error: 'JSONPath 语法暂不支持该写法' }
    last = m.index + m[0].length
    if (m[1]) list.push({ type: 'key', key: m[1] })
    else if (m[2] != null) list.push({ type: 'index', index: Number(m[2]) })
    else if (m[0].includes('[*]')) list.push({ type: 'wildcard' })
    else if (m[3] != null) list.push({ type: 'key', key: m[3] })
    else if (m[4] != null) list.push({ type: 'key', key: m[4] })
    else if (m[5] === '*') list.push({ type: 'wildcard' })
  }
  if (last !== p.length) return { list: [], error: 'JSONPath 语法暂不支持该写法' }
  return { list, error: '' }
}

function walk(node, tokens, i) {
  if (i >= tokens.length) return [node]
  if (node == null) return []
  const t = tokens[i]
  if (t.type === 'wildcard') {
    if (!Array.isArray(node)) return []
    return node.flatMap((item) => walk(item, tokens, i + 1))
  }
  if (t.type === 'index') {
    if (!Array.isArray(node) || t.index < 0 || t.index >= node.length) return []
    return walk(node[t.index], tokens, i + 1)
  }
  if (typeof node !== 'object' || Array.isArray(node)) return []
  if (!(t.key in node)) return []
  return walk(node[t.key], tokens, i + 1)
}

export function formatJsonPathResult(matches) {
  if (!matches.length) return { text: '不匹配', empty: true }
  const value = matches.length === 1 ? matches[0] : matches
  if (value === undefined) return { text: '不匹配', empty: true }
  if (typeof value === 'string') return { text: value, empty: false }
  try {
    return { text: JSON.stringify(value, null, 2), empty: false }
  } catch {
    return { text: String(value), empty: false }
  }
}
