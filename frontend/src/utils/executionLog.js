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

function extractTime(message) {
  if (!message) return null
  const match = message.match(/^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}|\d{2}:\d{2}:\d{2}[.:]?\d*)/)
  return match ? match[1] : null
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
