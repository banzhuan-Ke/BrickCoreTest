/** App Inspector：定位器推荐、XPath、u2 代码片段 */

function escapeXPath(value) {
  return String(value ?? '').replace(/"/g, '\\"')
}

function escapePyString(value) {
  return String(value ?? '').replace(/\\/g, '\\\\').replace(/"/g, '\\"')
}

/**
 * 推荐平台定位器（与 runner suggest_locator 一致）
 * @param {object|null} node
 * @returns {{ by: string, value: string|object, index: number }|null}
 */
export function suggestLocator(node) {
  if (!node) return null
  const rid = (node.resource_id || '').trim()
  if (rid) return { by: 'resource_id', value: rid, index: 1 }
  const text = (node.text || '').trim()
  if (text) return { by: 'text', value: text, index: 1 }
  const desc = (node.content_desc || '').trim()
  if (desc) return { by: 'description', value: desc, index: 1 }
  const bounds = node.rect
  if (bounds?.width > 0 && bounds?.height > 0) {
    const cx = bounds.x + Math.floor(bounds.width / 2)
    const cy = bounds.y + Math.floor(bounds.height / 2)
    return { by: 'coordinates', value: { x: cx, y: cy }, index: 1 }
  }
  return null
}

/** 备选 XPath（多属性组合，尽量稳定） */
export function suggestXpath(node) {
  if (!node) return null
  const parts = []
  const rid = (node.resource_id || '').trim()
  const text = (node.text || '').trim()
  const desc = (node.content_desc || '').trim()
  const cls = (node.class || '').trim()

  if (rid) parts.push(`@resource-id="${escapeXPath(rid)}"`)
  if (text) parts.push(`@text="${escapeXPath(text)}"`)
  if (desc && !text) parts.push(`@content-desc="${escapeXPath(desc)}"`)

  if (parts.length) return `//*[${parts.join(' and ')}]`
  if (cls) return `//*[@class="${escapeXPath(cls)}"]`
  return null
}

export function formatLocatorText(locator) {
  if (!locator) return ''
  if (locator.by === 'coordinates' && locator.value && typeof locator.value === 'object') {
    const { x, y } = locator.value
    return `coordinates = (${x}, ${y})`
  }
  return `${locator.by} = ${locator.value}`
}

export function formatLocatorJson(locator) {
  if (!locator) return ''
  return JSON.stringify(locator, null, 2)
}

/** uiautomator2 Python 选择器片段 */
export function buildU2Code(node) {
  if (!node) return null
  const kwargs = []
  const rid = (node.resource_id || '').trim()
  const text = (node.text || '').trim()
  const desc = (node.content_desc || '').trim()

  if (rid) kwargs.push(`resourceId="${escapePyString(rid)}"`)
  if (text) kwargs.push(`text="${escapePyString(text)}"`)
  if (desc && !text) kwargs.push(`description="${escapePyString(desc)}"`)

  if (kwargs.length) return `d(${kwargs.join(', ')})`

  const xpath = suggestXpath(node)
  if (xpath) return `d.xpath('${escapePyString(xpath)}')`

  const r = node.rect
  if (r?.width > 0 && r?.height > 0) {
    const cx = r.x + Math.floor(r.width / 2)
    const cy = r.y + Math.floor(r.height / 2)
    return `d.click(${cx}, ${cy})`
  }
  return null
}

const BOOL_LABELS = {
  checkable: 'checkable',
  checked: 'checked',
  focusable: 'focusable',
  focused: 'focused',
  scrollable: 'scrollable',
  long_clickable: 'long-clickable',
  password: 'password',
  selected: 'selected',
  visible_to_user: 'visible-to-user',
}

function formatBool(v) {
  if (v === true) return 'true'
  if (v === false) return 'false'
  return v ?? '-'
}

function formatRect(rect) {
  if (!rect) return '-'
  const { x, y, width, height } = rect
  return `[${x},${y}][${x + width},${y + height}]`
}

/** 主属性区（对齐 uiauto.dev 常用字段） */
export function getPrimaryAttributes(node) {
  if (!node) return []
  return [
    { key: 'resource_id', label: 'ResourceId', value: node.resource_id || '-', copyable: !!node.resource_id?.trim() },
    { key: 'text', label: 'Text', value: node.text || '-', copyable: !!node.text?.trim() },
    { key: 'class', label: 'Class', value: node.class || '-', copyable: !!node.class?.trim() },
    { key: 'content_desc', label: 'ContentDesc', value: node.content_desc || '-', copyable: !!node.content_desc?.trim() },
    { key: 'package', label: 'Package', value: node.package || '-', copyable: !!node.package?.trim() },
    { key: 'enabled', label: 'Enabled', value: formatBool(node.enabled), copyable: false },
    { key: 'clickable', label: 'Clickable', value: formatBool(node.clickable), copyable: false },
    { key: 'rect', label: 'Bounds', value: formatRect(node.rect), copyable: !!node.rect },
  ]
}

/** 折叠区：其余布尔与原始字段 */
export function getExtraAttributes(node) {
  if (!node) return []
  const rows = []
  const extra = node.extra || {}

  for (const [field, label] of Object.entries(BOOL_LABELS)) {
    if (field in extra) {
      rows.push({ key: field, label, value: formatBool(extra[field]) })
    } else if (field in node && field !== 'enabled' && field !== 'clickable') {
      rows.push({ key: field, label, value: formatBool(node[field]) })
    }
  }

  if (extra.bounds) {
    rows.push({ key: 'bounds_raw', label: 'bounds (raw)', value: extra.bounds })
  }
  if (extra.node_index !== undefined && extra.node_index !== '') {
    rows.push({ key: 'node_index', label: 'index', value: String(extra.node_index) })
  }
  if (node.index !== undefined) {
    rows.push({ key: 'tree_index', label: 'tree path', value: String(node.index) })
  }

  return rows
}
