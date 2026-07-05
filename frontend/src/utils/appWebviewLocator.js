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

export function suggestWebLocator(node) {
  if (!node) return null
  const testid = (node.data_testid || '').trim()
  if (testid) {
    return { context: 'webview', by: 'css', value: `[data-testid="${testid}"]`, index: 1 }
  }
  const id = (node.id || '').trim()
  if (id) {
    return { context: 'webview', by: 'id', value: id, index: 1 }
  }
  const css = (node.css || '').trim()
  if (css && !['div', 'span', 'body'].includes(css)) {
    return { context: 'webview', by: 'css', value: css, index: 1 }
  }
  const xpath = (node.xpath || '').trim()
  if (xpath) {
    return { context: 'webview', by: 'xpath', value: xpath, index: 1 }
  }
  const text = (node.text || '').trim()
  if (text && text.length < 40) {
    return { context: 'webview', by: 'text', value: text, index: 1 }
  }
  return { context: 'webview', by: 'css', value: css || 'body', index: 1 }
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
