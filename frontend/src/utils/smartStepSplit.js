/**
 * 解析智能步骤 intent 中的编号列表，支持：
 * 1. xxx / 1、xxx / 1) xxx / 1）xxx
 * @param {string} raw
 * @returns {string[]}
 */
export function splitSmartStepIntents(raw) {
  const text = String(raw || '').trim()
  if (!text) return []

  const lines = text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean)
  if (lines.length <= 1) return [text]

  const numberedPattern = /^\d+\s*[.、)）]\s*(.+)$/
  const numberedCount = lines.filter((line) => numberedPattern.test(line)).length
  if (numberedCount < 2) return [text]

  const intents = []
  for (const line of lines) {
    const match = line.match(numberedPattern)
    if (match) {
      intents.push(match[1].trim())
    } else if (intents.length > 0) {
      intents[intents.length - 1] = `${intents[intents.length - 1]}\n${line}`
    } else {
      intents.push(line)
    }
  }

  return intents.length >= 2 ? intents : [text]
}
