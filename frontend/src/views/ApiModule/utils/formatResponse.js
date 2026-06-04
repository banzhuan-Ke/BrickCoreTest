/**
 * 尝试将响应体解析为 JSON 对象（兼容 JSON 字符串、对象、Python dict 字面量字符串）
 * @returns {{ parsed: any } | null}
 */
export function tryParseResponseJson(data) {
  if (data === null || data === undefined) return null
  if (typeof data === 'object') {
    return { parsed: data }
  }

  const str = String(data).trim()
  if (!str) return null

  try {
    return { parsed: JSON.parse(str) }
  } catch {
    if ((str.startsWith('{') && str.endsWith('}')) || (str.startsWith('[') && str.endsWith(']'))) {
      try {
        const normalized = str
          .replace(/\bNone\b/g, 'null')
          .replace(/\bTrue\b/g, 'true')
          .replace(/\bFalse\b/g, 'false')
          .replace(/'/g, '"')
        return { parsed: JSON.parse(normalized) }
      } catch {
        return null
      }
    }
    return null
  }
}

/** 是否可将响应体格式化为 JSON */
export function isResponseJsonFormattable(data) {
  return tryParseResponseJson(data) !== null
}

/**
 * 将响应体格式化为可读的 JSON 文本（兼容 JSON 字符串、对象、Python dict 字面量字符串）
 */
export function formatResponseJson(data) {
  const parsed = tryParseResponseJson(data)
  if (parsed) {
    try {
      return JSON.stringify(parsed.parsed, null, 2)
    } catch {
      return String(data)
    }
  }
  if (data === null || data === undefined) return ''
  return String(data).trim()
}

/** 将响应体压缩为单行 JSON 文本 */
export function compactResponseJson(data) {
  const parsed = tryParseResponseJson(data)
  if (parsed) {
    try {
      return JSON.stringify(parsed.parsed)
    } catch {
      return String(data)
    }
  }
  if (data === null || data === undefined) return ''
  return String(data).trim().replace(/\s+/g, ' ')
}

/**
 * 按展示模式格式化响应体
 * @param {'pretty' | 'compact' | 'raw'} mode
 */
export function formatResponseBody(data, mode = 'pretty') {
  if (mode === 'compact') return compactResponseJson(data)
  if (mode === 'pretty' && isResponseJsonFormattable(data)) return formatResponseJson(data)
  if (data === null || data === undefined) return ''
  if (typeof data === 'object') {
    try {
      return JSON.stringify(data, null, 2)
    } catch {
      return String(data)
    }
  }
  return String(data).trim()
}
