/**
 * 接口响应示例：支持标准 JSON 对象，以及 SSE 等原始文本（event:/data: 多行）
 */

export function formatResponseExample(example) {
  if (example == null || example === '') return ''
  if (typeof example === 'string') return example
  try {
    return JSON.stringify(example, null, 2)
  } catch {
    return String(example)
  }
}

/** 编辑框 → 存库：能解析为 JSON 则存对象，否则存原始字符串 */
export function parseResponseExampleInput(val) {
  if (val == null || String(val).trim() === '') return null
  const text = String(val)
  try {
    return JSON.parse(text)
  } catch {
    return text
  }
}

/** 从 JSON 或 SSE（data: 行）中提取对象，供 Schema 一键生成 */
export function parseResponseExampleAsJson(text) {
  const trimmed = String(text || '').trim()
  if (!trimmed) return null
  try {
    return JSON.parse(trimmed)
  } catch {
    /* SSE / 类 SSE 文本 */
  }
  const dataLines = []
  for (const line of trimmed.split(/\r?\n/)) {
    const m = line.match(/^data:\s*(.*)$/i)
    if (m) {
      const payload = m[1].trim()
      if (payload && payload !== '[DONE]') dataLines.push(payload)
    }
  }
  if (dataLines.length === 1) {
    try {
      return JSON.parse(dataLines[0])
    } catch {
      return null
    }
  }
  if (dataLines.length > 1) {
    const objs = []
    for (const p of dataLines) {
      try {
        objs.push(JSON.parse(p))
      } catch {
        /* 跳过非 JSON 行 */
      }
    }
    if (objs.length === 1) return objs[0]
    if (objs.length > 1) return objs
  }
  return null
}
