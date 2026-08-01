/** App Inspector WebView / H5 DOM 定位器 */

export function isWebViewNativeNode(node) {
  if (!node) return false
  return String(node.class || '').toLowerCase().includes('webview')
}

export function formatWebNodeLabel(node) {
  if (!node) return '(node)'
  const testid = (node.data_testid || '').trim()
  if (testid) return `[testid] ${testid}`
  const text = (node.text || '').trim()
  if (text) return text.slice(0, 40)
  const id = (node.id || '').trim()
  if (id) return `#${id}`
  const tag = (node.tag || 'node').toLowerCase()
  const cls = (node.class || '').trim().split(/\s+/)[0]
  return cls ? `${tag}.${cls}` : tag
}

export function decorateWebNodes(nodes) {
  return (nodes || []).map((n) => ({
    ...n,
    label: formatWebNodeLabel(n),
    children: decorateWebNodes(n.children),
  }))
}

export function formatWebContextLabel(ctx, idx) {
  const title = (ctx?.title || '').trim() || `页面 ${idx + 1}`
  const url = (ctx?.url || '').trim()
  const src = ctx?.source === 'chrome' ? '[Chrome] ' : ctx?.source === 'webview' ? '[WebView] ' : ''
  if (url) return `${src}${title} — ${url.slice(0, 60)}`
  return `${src}${title}`
}

function _webCandidateKey(loc) {
  if (!loc?.by) return ''
  return `${String(loc.by).toLowerCase()}::${String(loc.value ?? '').trim()}::${loc.index || 1}`
}

function _asWebCandidate(loc) {
  if (!loc?.by) return null
  const value = loc.value
  if (value == null || String(value).trim() === '') return null
  return {
    context: 'webview',
    by: String(loc.by).trim(),
    value,
    index: Number(loc.index) > 0 ? Number(loc.index) : 1,
  }
}

/** H5 有序候选：testid css → id → css → xpath → text */
export function buildWebLocatorCandidates(node) {
  if (!node) return []
  const out = []
  const push = (loc) => {
    const item = _asWebCandidate(loc)
    if (!item) return
    const key = _webCandidateKey(item)
    if (out.some((x) => _webCandidateKey(x) === key)) return
    out.push(item)
  }

  const testid = (node.data_testid || '').trim()
  if (testid) push({ by: 'css', value: `[data-testid="${testid}"]`, index: 1 })

  const id = (node.id || '').trim()
  if (id) push({ by: 'id', value: id, index: 1 })

  const css = (node.css || '').trim()
  if (css && !['div', 'span', 'body'].includes(css)) {
    push({ by: 'css', value: css, index: 1 })
  }

  const xpath = (node.xpath || '').trim()
  if (xpath) push({ by: 'xpath', value: xpath, index: 1 })

  const text = (node.text || '').trim()
  if (text && text.length < 40) push({ by: 'text', value: text, index: 1 })

  if (!out.length && css) push({ by: 'css', value: css, index: 1 })
  if (!out.length) push({ by: 'css', value: 'body', index: 1 })
  return out
}

export function suggestWebLocator(node) {
  const candidates = buildWebLocatorCandidates(node)
  return candidates[0] || null
}

export function formatWebLocatorCandidateLabel(loc) {
  if (!loc?.by) return ''
  const v = String(loc.value ?? '')
  const short = v.length > 48 ? `${v.slice(0, 48)}…` : v
  return `${loc.by} = ${short}`
}

/**
 * H5 探查保存：默认最优 + 全量候选
 * @param {object|null} node
 * @param {object|null} preferred
 * @param {{ page_index?: number, devtools_source?: string }} extras
 */
export function buildWebLocatorPayload(node, preferred = null, extras = {}) {
  const candidates = buildWebLocatorCandidates(node)
  if (!candidates.length) return null

  let primary = _asWebCandidate(preferred)
  if (!primary || !candidates.some((c) => _webCandidateKey(c) === _webCandidateKey(primary))) {
    primary = candidates[0]
  }
  const rest = candidates.filter((c) => _webCandidateKey(c) !== _webCandidateKey(primary))
  const ordered = [primary, ...rest]

  return {
    context: 'webview',
    by: primary.by,
    value: primary.value,
    index: primary.index || 1,
    page_index: extras.page_index ?? 0,
    devtools_source: extras.devtools_source || 'webview',
    candidates: ordered,
    meta: {
      tag: node?.tag || '',
      id: node?.id || '',
      class: node?.class || '',
      text: node?.text || '',
      data_testid: node?.data_testid || '',
      css: node?.css || '',
      xpath: node?.xpath || '',
    },
  }
}

export function promoteWebLocatorCandidate(locator, candidate) {
  if (!locator || typeof locator !== 'object') return locator
  const pick = _asWebCandidate(candidate)
  if (!pick) return locator
  const existing = Array.isArray(locator.candidates)
    ? locator.candidates.map(_asWebCandidate).filter(Boolean)
    : []
  const rest = existing.filter((c) => _webCandidateKey(c) !== _webCandidateKey(pick))
  locator.context = 'webview'
  locator.by = pick.by
  locator.value = pick.value
  locator.index = pick.index || 1
  locator.candidates = [pick, ...rest]
  return locator
}

export function getWebPrimaryAttributes(node) {
  if (!node) return []
  return [
    { key: 'tag', label: 'Tag', value: node.tag || '-', copyable: !!node.tag },
    { key: 'id', label: 'Id', value: node.id || '-', copyable: !!node.id?.trim() },
    { key: 'class', label: 'Class', value: node.class || '-', copyable: !!node.class?.trim() },
    { key: 'text', label: 'Text', value: node.text || '-', copyable: !!node.text?.trim() },
    { key: 'data_testid', label: 'data-testid', value: node.data_testid || '-', copyable: !!node.data_testid?.trim() },
    { key: 'role', label: 'Role', value: node.role || '-', copyable: !!node.role?.trim() },
    { key: 'css', label: 'CSS', value: node.css || '-', copyable: !!node.css?.trim() },
    { key: 'xpath', label: 'XPath', value: node.xpath || '-', copyable: !!node.xpath?.trim() },
  ]
}

export function formatWebLocatorText(locator) {
  if (!locator) return ''
  return `[${locator.context || 'webview'}] ${locator.by} = ${locator.value}`
}

export function formatWebLocatorJson(locator) {
  if (!locator) return ''
  return JSON.stringify(locator, null, 2)
}

export function buildWebPlaywrightHint(node) {
  const loc = suggestWebLocator(node)
  if (!loc) return null
  if (loc.by === 'css') return `page.locator('${String(loc.value).replace(/'/g, "\\'")}')`
  if (loc.by === 'xpath') return `page.locator('xpath=${String(loc.value).replace(/'/g, "\\'")}')`
  if (loc.by === 'text') return `page.get_by_text('${String(loc.value).replace(/'/g, "\\'")}')`
  return null
}
