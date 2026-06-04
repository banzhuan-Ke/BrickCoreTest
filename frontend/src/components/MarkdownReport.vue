<template>
  <div class="markdown-report" :class="{ compact }" :style="wrapStyle" v-html="html" />
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  content: { type: String, default: '' },
  maxHeight: { type: String, default: '' },
  compact: { type: Boolean, default: false }
})

const wrapStyle = computed(() => {
  if (!props.maxHeight || props.maxHeight === 'none') return {}
  return { maxHeight: props.maxHeight, overflow: 'auto' }
})

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function inlineFormat(text) {
  let s = escapeHtml(text)
  s = s.replace(/\[([^\]]+)\]\((#[^)]+)\)/g, '<a class="md-link" href="$2">$1</a>')
  s = s.replace(/\[([^\]]+)\]\((\/[^)]+)\)/g, '<a class="md-link" href="#$2">$1</a>')
  s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  s = s.replace(/`([^`]+)`/g, '<code>$1</code>')
  return s
}

function isTableRow(line) {
  const t = line.trim()
  return t.startsWith('|') && t.includes('|', 1)
}

function isTableSeparator(line) {
  return /^\|[\s\-:|]+\|$/.test(line.trim())
}

function parseTableCells(line) {
  const trimmed = line.trim()
  const inner = trimmed.startsWith('|') ? trimmed.slice(1) : trimmed
  const body = inner.endsWith('|') ? inner.slice(0, -1) : inner
  return body.split('|').map((c) => c.trim())
}

function renderTableBlock(rows) {
  if (!rows.length) return ''
  let headerCells = parseTableCells(rows[0])
  let bodyStart = 1
  if (rows.length > 1 && isTableSeparator(rows[1])) {
    bodyStart = 2
  }
  const thead = `<thead><tr>${headerCells.map((c) => `<th>${inlineFormat(c)}</th>`).join('')}</tr></thead>`
  const bodyRows = rows.slice(bodyStart).map((row) => {
    const cells = parseTableCells(row)
    return `<tr>${cells.map((c) => `<td>${inlineFormat(c)}</td>`).join('')}</tr>`
  })
  const tbody = bodyRows.length ? `<tbody>${bodyRows.join('')}</tbody>` : ''
  return `<div class="md-table-wrap"><table class="md-table">${thead}${tbody}</table></div>`
}

function splitBlocks(md) {
  const lines = String(md).replace(/\r/g, '').split('\n')
  const blocks = []
  let i = 0

  const skipEmpty = () => {
    while (i < lines.length && !lines[i].trim()) i += 1
  }

  while (i < lines.length) {
    skipEmpty()
    if (i >= lines.length) break

    const trimmed = lines[i].trim()

    // Markdown table block（允许行间空行）
    if (isTableRow(trimmed)) {
      const tableRows = [lines[i]]
      i += 1
      while (i < lines.length) {
        if (!lines[i].trim()) {
          let j = i + 1
          while (j < lines.length && !lines[j].trim()) j += 1
          if (j < lines.length && isTableRow(lines[j].trim())) {
            i = j
            tableRows.push(lines[i])
            i += 1
            continue
          }
          break
        }
        if (isTableRow(lines[i].trim()) || isTableSeparator(lines[i].trim())) {
          tableRows.push(lines[i])
          i += 1
        } else {
          break
        }
      }
      blocks.push({ type: 'table', rows: tableRows })
      continue
    }

    if (trimmed.startsWith('# ')) {
      blocks.push({ type: 'h1', text: trimmed.slice(2) })
      i += 1
      continue
    }
    if (trimmed.startsWith('## ')) {
      blocks.push({ type: 'h2', text: trimmed.slice(3) })
      i += 1
      continue
    }
    if (trimmed.startsWith('### ')) {
      blocks.push({ type: 'h3', text: trimmed.slice(4) })
      i += 1
      continue
    }
    if (trimmed.startsWith('#### ')) {
      blocks.push({ type: 'h4', text: trimmed.slice(5) })
      i += 1
      continue
    }
    if (trimmed === '---' || trimmed === '***') {
      blocks.push({ type: 'hr' })
      i += 1
      continue
    }
    if (/^[-*]\s+/.test(trimmed)) {
      const items = []
      while (i < lines.length) {
        const t = lines[i].trim()
        if (!t) {
          const next = lines.slice(i + 1).find((l) => l.trim())
          if (next && /^[-*]\s+/.test(next.trim())) {
            i += 1
            continue
          }
          break
        }
        if (/^[-*]\s+/.test(t)) {
          items.push(t.replace(/^[-*]\s+/, ''))
          i += 1
        } else {
          break
        }
      }
      blocks.push({ type: 'ul', items })
      continue
    }
    if (/^\d+\.\s+/.test(trimmed)) {
      blocks.push({ type: 'ol', text: trimmed })
      i += 1
      continue
    }

    // 普通段落：合并连续短行，减少多余空行
    const paraLines = [lines[i]]
    i += 1
    while (i < lines.length) {
      const t = lines[i].trim()
      if (!t) {
        const next = lines.slice(i + 1).find((l) => l.trim())
        if (!next) break
        if (
          next.startsWith('#') ||
          isTableRow(next) ||
          /^[-*]\s+/.test(next) ||
          /^\d+\.\s+/.test(next) ||
          next === '---' ||
          next === '***'
        ) {
          break
        }
        i += 1
        continue
      }
      if (
        t.startsWith('#') ||
        isTableRow(t) ||
        /^[-*]\s+/.test(t) ||
        /^\d+\.\s+/.test(t) ||
        t === '---' ||
        t === '***'
      ) {
        break
      }
      paraLines.push(lines[i])
      i += 1
    }
    blocks.push({ type: 'p', lines: paraLines })
  }

  return blocks
}

function renderBlocks(blocks) {
  const parts = []
  for (const block of blocks) {
    switch (block.type) {
      case 'h1':
        parts.push(`<h1 class="md-h1">${inlineFormat(block.text)}</h1>`)
        break
      case 'h2':
        parts.push(`<h2 class="md-h2">${inlineFormat(block.text)}</h2>`)
        break
      case 'h3':
        parts.push(`<h3 class="md-h3">${inlineFormat(block.text)}</h3>`)
        break
      case 'h4':
        parts.push(`<h4 class="md-h4">${inlineFormat(block.text)}</h4>`)
        break
      case 'hr':
        parts.push('<hr class="md-hr" />')
        break
      case 'ul':
        parts.push(
          `<ul class="md-ul">${block.items.map((item) => `<li>${inlineFormat(item)}</li>`).join('')}</ul>`
        )
        break
      case 'ol':
        parts.push(`<p class="md-ol-item">${inlineFormat(block.text)}</p>`)
        break
      case 'table':
        parts.push(renderTableBlock(block.rows))
        break
      case 'p':
        parts.push(
          `<p class="md-p">${block.lines.map((l) => inlineFormat(l.trim())).join('<br/>')}</p>`
        )
        break
      default:
        break
    }
  }
  return parts.join('')
}

function renderMarkdown(md) {
  if (!md || !String(md).trim()) {
    return '<p class="empty-tip">暂无内容</p>'
  }
  const normalized = String(md)
    .replace(/\r/g, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
  return renderBlocks(splitBlocks(normalized))
}

const html = computed(() => renderMarkdown(props.content))
</script>

<style scoped>
.markdown-report {
  font-size: 14px;
  line-height: 1.75;
  color: #303133;
  background: #fff;
  padding: 20px 24px;
  border-radius: 8px;
  border: 1px solid #ebeef5;
}

.markdown-report.compact {
  font-size: 13px;
  line-height: 1.55;
  padding: 6px 8px;
  border: none;
  background: transparent;
}

.markdown-report :deep(.empty-tip) {
  color: #909399;
  text-align: center;
  padding: 24px;
}

.markdown-report :deep(.md-h1) {
  font-size: 22px;
  font-weight: 600;
  color: #1a1a1a;
  margin: 0 0 16px;
  padding-bottom: 12px;
  border-bottom: 2px solid #409eff;
}

.markdown-report.compact :deep(.md-h1) {
  font-size: 15px;
  margin: 0 0 8px;
  padding-bottom: 6px;
  border-bottom-width: 1px;
}

.markdown-report :deep(.md-h2) {
  font-size: 17px;
  font-weight: 600;
  color: #303133;
  margin: 24px 0 12px;
  padding-left: 10px;
  border-left: 4px solid #409eff;
}

.markdown-report.compact :deep(.md-h2) {
  font-size: 14px;
  margin: 10px 0 6px;
  padding-left: 8px;
  border-left-width: 3px;
}

.markdown-report :deep(.md-h3) {
  font-size: 15px;
  font-weight: 600;
  color: #606266;
  margin: 16px 0 8px;
}

.markdown-report.compact :deep(.md-h3) {
  font-size: 13px;
  margin: 8px 0 4px;
}

.markdown-report :deep(.md-h4) {
  font-size: 14px;
  font-weight: 600;
  color: #909399;
  margin: 12px 0 6px;
}

.markdown-report.compact :deep(.md-h4) {
  font-size: 13px;
  margin: 6px 0 4px;
}

.markdown-report :deep(.md-p) {
  margin: 8px 0;
  text-align: justify;
}

.markdown-report.compact :deep(.md-p) {
  margin: 2px 0;
  text-align: left;
}

.markdown-report :deep(.md-ul) {
  margin: 8px 0 12px;
  padding-left: 0;
  list-style: none;
}

.markdown-report.compact :deep(.md-ul) {
  margin: 4px 0 6px;
}

.markdown-report :deep(.md-ul li) {
  position: relative;
  padding: 6px 0 6px 18px;
  margin: 0;
  border-bottom: 1px dashed #f0f0f0;
}

.markdown-report.compact :deep(.md-ul li) {
  padding: 2px 0 2px 16px;
  border-bottom: none;
}

.markdown-report :deep(.md-ul li:last-child) {
  border-bottom: none;
}

.markdown-report :deep(.md-ul li::before) {
  content: '';
  position: absolute;
  left: 4px;
  top: 14px;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #409eff;
}

.markdown-report.compact :deep(.md-ul li::before) {
  top: 9px;
  width: 5px;
  height: 5px;
}

.markdown-report :deep(.md-ol-item) {
  margin: 4px 0;
  padding-left: 8px;
}

.markdown-report :deep(.md-table-wrap) {
  overflow-x: auto;
  margin: 8px 0;
  border-radius: 6px;
  border: 1px solid #ebeef5;
}

.markdown-report.compact :deep(.md-table-wrap) {
  margin: 6px 0;
}

.markdown-report :deep(.md-table) {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  line-height: 1.45;
}

.markdown-report :deep(.md-table th),
.markdown-report :deep(.md-table td) {
  padding: 6px 10px;
  border: 1px solid #ebeef5;
  text-align: left;
  vertical-align: top;
  word-break: break-word;
}

.markdown-report :deep(.md-table th) {
  background: #f5f7fa;
  font-weight: 600;
  color: #303133;
  white-space: nowrap;
}

.markdown-report :deep(.md-table tr:nth-child(even) td) {
  background: #fafafa;
}

.markdown-report :deep(strong) {
  color: #303133;
  font-weight: 600;
}

.markdown-report :deep(code) {
  background: #f5f7fa;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 13px;
  color: #c7254e;
}

.markdown-report :deep(a.md-link) {
  color: #409eff;
  text-decoration: none;
  border-bottom: 1px dashed rgba(64, 158, 255, 0.45);
}

.markdown-report :deep(a.md-link:hover) {
  color: #66b1ff;
  border-bottom-style: solid;
}

.markdown-report :deep(.md-hr) {
  border: none;
  border-top: 1px solid #ebeef5;
  margin: 20px 0;
}

.markdown-report.compact :deep(.md-hr) {
  margin: 10px 0;
}
</style>
