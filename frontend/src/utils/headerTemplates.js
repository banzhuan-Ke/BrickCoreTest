/** Header 模板工具函数 */

export function normalizeTemplateHeaderList(raw, { keepEmpty = false } = {}) {
  if (!raw) return []
  if (Array.isArray(raw)) {
    return raw
      .filter((h) => h && (keepEmpty || h.key))
      .map((h) => ({
        key: String(h.key || '').trim(),
        value: h.value ?? '',
        description: h.description ?? '',
      }))
  }
  if (typeof raw === 'object') {
    return Object.entries(raw).map(([key, value]) => ({
      key,
      value: value ?? '',
      description: '',
    }))
  }
  return []
}

export function validateTemplateHeaders(list) {
  const items = normalizeTemplateHeaderList(list)
  const seen = new Set()
  for (const item of items) {
    if (!item.key) return { ok: false, error: 'Header 名称不能为空' }
    if (seen.has(item.key)) return { ok: false, error: `Header key 重复: ${item.key}` }
    seen.add(item.key)
  }
  return { ok: true, items }
}

/** 从模板导入：跳过本地已有 key，仅追加新项 */
export function importTemplateHeadersToLocal(localHeaders, templateHeaders) {
  const local = normalizeTemplateHeaderList(localHeaders, { keepEmpty: true })
  const localKeys = new Set(local.map((h) => h.key).filter(Boolean))
  const imported = []
  const skipped = []
  normalizeTemplateHeaderList(templateHeaders).forEach((item) => {
    if (localKeys.has(item.key)) {
      skipped.push(item.key)
      return
    }
    local.push({
      key: item.key,
      value: item.value,
      description: item.description
        ? `来自模板: ${item.description}`
        : '来自 Header 模板',
    })
    localKeys.add(item.key)
    imported.push(item.key)
  })
  return { headers: local, imported, skipped }
}
