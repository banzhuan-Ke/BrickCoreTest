/** 虚拟滚动单行高度（px），与 ExecutionLogScroller 样式保持一致 */
export const EXECUTION_LOG_ROW_HEIGHT = 28

const LEVEL_KEYWORDS = {
  error: ['error', 'exception', '失败', 'failed'],
  warning: ['warn', 'warning'],
  success: ['success', 'pass', '通过'],
  debug: ['debug']
}

function detectLevel(text, fallback = 'info') {
  const lower = (text || '').toLowerCase()
  for (const [level, keywords] of Object.entries(LEVEL_KEYWORDS)) {
    if (keywords.some((kw) => lower.includes(kw))) return level
  }
  return fallback
}

const LOG_TIME_RE = /(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}|\d{2}:\d{2}:\d{2}[.:]?\d*)/

/**
 * 从日志正文提取发生时间（非接收时间）。
 * 兼容：行首时间、【LEVEL】/ [LEVEL] 后紧跟时间（设备实时日志）。
 */
export function extractTime(message) {
  if (!message) return null
  const text = String(message)
  // [HH:mm:ss] [LEVEL] msg（报告日志常见）
  const bracketed = text.match(/^\[(\d{2}:\d{2}:\d{2}[.:]?\d*)\]/)
  if (bracketed) return bracketed[1]
  // 行首时间，或 【LEVEL】/[LEVEL] 后紧跟时间（设备实时日志）
  const head = text.match(
    new RegExp(`^(?:[【\\[]\\w+[】\\]]\\s+)?${LOG_TIME_RE.source}`)
  )
  return head ? head[1] : null
}

/** 设备日志左侧时间列：优先 HH:mm:ss，便于与现有布局对齐 */
export function formatLogTimeShort(rawTime) {
  if (!rawTime) return null
  const full = String(rawTime).match(/\d{4}-\d{2}-\d{2}\s+(\d{2}:\d{2}:\d{2})/)
  if (full) return full[1]
  const hm = String(rawTime).match(/^(\d{2}:\d{2}:\d{2})/)
  return hm ? hm[1] : String(rawTime)
}

function parseStringLog(log, index) {
  const result = { message: log, index, level: 'info', time: null }

  const bracketMatch = log.match(/^\[(\d{2}:\d{2}:\d{2}[.:]?\d*)\]?\s*\[(\w+)\]?\s*(.*)/i)
  if (bracketMatch) {
    result.time = bracketMatch[1]
    result.level = bracketMatch[2].toLowerCase()
    result.message = bracketMatch[3]
    return result
  }

  result.level = detectLevel(log)
  result.time = extractTime(log)
  return result
}

/**
 * 解析单条执行日志（兼容 Runner 的 [level, message] 元组、对象、字符串）
 */
export function parseExecutionLogEntry(log, index) {
  if (Array.isArray(log)) {
    const head = String(log[0] || '').trim()
    const upperHead = head.toUpperCase()
    if (log.length >= 2 && ['INFO', 'ERROR', 'WARNING', 'WARN', 'DEBUG', 'SUCCESS'].includes(upperHead)) {
      const message = String(log[1])
      return {
        index,
        level: upperHead === 'WARN' ? 'warning' : head.toLowerCase(),
        message,
        time: extractTime(message)
      }
    }
    const message = log.map((part) => String(part)).join(' ')
    return { index, level: detectLevel(message), message, time: extractTime(message) }
  }

  if (typeof log === 'object' && log !== null) {
    const message = log.message || log.msg || log.content || JSON.stringify(log)
    return {
      index,
      level: (log.level || detectLevel(message)).toLowerCase(),
      message: String(message),
      time: log.time || log.timestamp || extractTime(message)
    }
  }

  if (typeof log === 'string') {
    return parseStringLog(log, index)
  }

  const message = String(log)
  return { index, level: detectLevel(message), message, time: extractTime(message) }
}

export function parseExecutionLogs(logs) {
  return (logs || []).map((log, index) => parseExecutionLogEntry(log, index))
}
