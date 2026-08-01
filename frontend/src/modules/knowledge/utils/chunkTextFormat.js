/**
 * 将 RAG 分块文本（尤其 xlsx 导出的 pipe 分隔行）解析为表格或纯文本展示结构。
 */

function isSheetHeaderLine(line) {
  const t = (line || '').trim()
  return /^\[[^\]]+\]$/.test(t)
}

function splitPipeRow(line) {
  return (line || '').split('|').map((c) => c.trim())
}

/** 解析 `[表名]` 或 `[表名] 列1 | 列2` 行 */
function peelSheetPrefix(line) {
  const t = (line || '').trim()
  if (isSheetHeaderLine(t)) {
    return { sheetName: t.slice(1, -1), row: null }
  }
  const m = t.match(/^(\[[^\]]+\])\s*(.+)$/)
  if (m && m[2].includes('|')) {
    return { sheetName: m[1].slice(1, -1), row: m[2] }
  }
  return { sheetName: null, row: t }
}

function buildTableFromPipeLines(pipeLines, sheetName = null) {
  if (!pipeLines.length) return null

  const matrix = pipeLines.map(splitPipeRow)
  const colCount = Math.max(...matrix.map((r) => r.length))
  if (colCount < 2) return null

  const normalized = matrix.map((row) => {
    const copy = [...row]
    while (copy.length < colCount) copy.push('')
    return copy
  })

  const header = normalized[0]
  const body = normalized.length > 1 ? normalized.slice(1) : normalized
  const headerLooksValid = header.filter((c) => c).length >= Math.max(2, Math.floor(colCount * 0.35))

  const columns = Array.from({ length: colCount }, (_, i) => ({
    prop: `c${i}`,
    label: headerLooksValid && header[i] ? header[i] : `列${i + 1}`
  }))

  const rows = (headerLooksValid ? body : normalized).map((row) => {
    const obj = {}
    row.forEach((cell, i) => {
      obj[`c${i}`] = cell
    })
    return obj
  })

  return { sheetName, columns, rows }
}

/**
 * @param {string} text
 * @returns {{ kind: 'plain', text: string } | { kind: 'table', sheetName: string|null, columns: Array<{prop:string,label:string}>, rows: object[] } | { kind: 'mixed', plainText: string, table: object|null, text: string }}
 */
export function parseChunkDisplay(text) {
  const raw = (text || '').trim()
  if (!raw) return { kind: 'plain', text: '' }

  const lines = raw.split('\n').map((l) => l.trim()).filter(Boolean)
  if (!lines.length) return { kind: 'plain', text: raw }

  let sheetName = null
  const dataLines = []

  for (const line of lines) {
    const peeled = peelSheetPrefix(line)
    if (peeled.sheetName && !sheetName) {
      sheetName = peeled.sheetName
    }
    if (peeled.row) {
      dataLines.push(peeled.row)
    } else if (!peeled.sheetName) {
      dataLines.push(line)
    }
  }

  const pipeLines = dataLines.filter((l) => l.includes('|'))
  const plainLines = dataLines.filter((l) => !l.includes('|'))
  const plainText = plainLines.join('\n')
  const plainChars = plainText.length
  const pipeChars = pipeLines.join('\n').length

  if (pipeLines.length < 1) {
    return { kind: 'plain', text: raw }
  }

  const table = buildTableFromPipeLines(pipeLines, sheetName)
  if (!table) {
    return { kind: 'plain', text: raw }
  }

  // Word 等文档：大段正文 + 末尾小表格时，不能只渲染表格行而丢掉正文
  if (plainChars >= 40 && plainChars >= pipeChars * 0.15) {
    return {
      kind: 'mixed',
      plainText,
      table,
      text: raw
    }
  }

  return { kind: 'table', ...table }
}

/**
 * 合并上下文里按 RAG 分块头拆段，便于分段展示。
 */
export function splitContextBlocks(contextText) {
  const text = (contextText || '').trim()
  if (!text) return []
  const parts = text.split(/(?=--- 《)/).map((p) => p.trim()).filter(Boolean)
  if (parts.length <= 1 && !text.startsWith('---')) {
    return [{ header: null, body: text }]
  }
  return parts.map((part) => {
    const nl = part.indexOf('\n')
    if (part.startsWith('---') && nl > 0) {
      return { header: part.slice(0, nl).trim(), body: part.slice(nl + 1).trim() }
    }
    return { header: null, body: part }
  })
}

/**
 * AI 摘要按 ### 标题拆段（Map-Reduce 摘要格式）。
 */
export function splitDigestSections(text) {
  const raw = (text || '').trim()
  if (!raw) return []

  const parts = raw.split(/(?=^### )/m).map((p) => p.trim()).filter(Boolean)
  if (parts.length <= 1 && !raw.startsWith('### ')) {
    return [{ title: null, intro: raw, body: '' }]
  }

  const sections = []
  let intro = ''

  for (const part of parts) {
    if (!part.startsWith('### ')) {
      intro = part
      continue
    }
    const nl = part.indexOf('\n')
    const title = nl > 0 ? part.slice(4, nl).trim() : part.slice(4).trim()
    const body = nl > 0 ? part.slice(nl + 1).trim() : ''
    sections.push({ title, body })
  }

  if (!sections.length) {
    return [{ title: null, intro: raw, body: '' }]
  }
  if (intro) {
    sections.unshift({ title: null, intro, body: '' })
  }
  return sections
}

/** 清理问答回答中的模型思考过程标签 */
export function formatQaAnswer(text) {
  if (!text) return ''
  const openThink = '<' + 'think>'
  const closeThink = '</' + 'think>'
  const openRedacted = '<' + 'redacted_reasoning>'
  const closeRedacted = '</' + 'redacted_reasoning>'
  let s = String(text).trim()
  const blockRe = new RegExp(
    `(?:${openThink}[\\s\\S]*?${closeThink}|${openRedacted}[\\s\\S]*?${closeRedacted})`,
    'gi'
  )
  let prev = ''
  while (prev !== s) {
    prev = s
    s = s.replace(blockRe, '').trim()
  }
  const unclosedRe = new RegExp(
    `^(?:${openThink}|${openRedacted})[\\s\\S]*?(?:${closeThink}|${closeRedacted})\\s*`,
    'i'
  )
  s = s.replace(unclosedRe, '').trim()
  const onlyRe = new RegExp(`^(?:${openThink}|${openRedacted})[\\s\\S]*$`, 'i')
  if (onlyRe.test(s)) return ''
  return s
}
