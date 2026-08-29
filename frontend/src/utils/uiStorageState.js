/**
 * Web 登录态 storage_state 解析 / 摘要 / 表格编辑辅助
 */

export function emptyStorageState() {
  return { cookies: [], origins: [], sessionStorageOrigins: [] }
}

export function summarizeStorageState(doc) {
  const d = doc && typeof doc === 'object' ? doc : emptyStorageState()
  const cookies = Array.isArray(d.cookies) ? d.cookies : []
  const origins = Array.isArray(d.origins) ? d.origins : []
  const ss =
    Array.isArray(d.sessionStorageOrigins)
      ? d.sessionStorageOrigins
      : Array.isArray(d.session_storage_origins)
        ? d.session_storage_origins
        : []

  let lsKeys = 0
  const lsOrigins = []
  for (const o of origins) {
    if (!o || typeof o !== 'object') continue
    const origin = String(o.origin || '').trim()
    const items = Array.isArray(o.localStorage)
      ? o.localStorage
      : Array.isArray(o.local_storage)
        ? o.local_storage
        : []
    lsKeys += items.length
    if (origin) lsOrigins.push(origin)
  }

  let ssKeys = 0
  const ssOrigins = []
  for (const o of ss) {
    if (!o || typeof o !== 'object') continue
    const origin = String(o.origin || '').trim()
    const items = Array.isArray(o.sessionStorage)
      ? o.sessionStorage
      : Array.isArray(o.session_storage)
        ? o.session_storage
        : []
    ssKeys += items.length
    if (origin) ssOrigins.push(origin)
  }

  const domains = []
  for (const c of cookies) {
    const domain = String(c?.domain || '').trim()
    if (domain && !domains.includes(domain)) domains.push(domain)
  }

  return {
    cookies: cookies.length,
    localStorageKeys: lsKeys,
    localStorageOrigins: lsOrigins,
    sessionStorageKeys: ssKeys,
    sessionStorageOrigins: ssOrigins,
    cookieDomains: domains,
    hasSessionStorageExtension: ssKeys > 0,
  }
}

export function parseStorageStateText(text) {
  const raw = String(text || '').trim()
  if (!raw) return { ok: false, error: '内容为空' }
  let parsed
  try {
    parsed = JSON.parse(raw)
  } catch {
    return { ok: false, error: 'JSON 无效' }
  }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    return { ok: false, error: '须为 JSON 对象' }
  }
  if (
    !('cookies' in parsed)
    && !('origins' in parsed)
    && !('sessionStorageOrigins' in parsed)
    && !('session_storage_origins' in parsed)
  ) {
    return { ok: false, error: '须包含 cookies、origins 或 sessionStorageOrigins' }
  }
  const normalized = {
    cookies: Array.isArray(parsed.cookies) ? parsed.cookies.map((c) => ({ ...c })) : [],
    origins: Array.isArray(parsed.origins) ? parsed.origins.map((o) => ({ ...o })) : [],
    sessionStorageOrigins: Array.isArray(parsed.sessionStorageOrigins)
      ? parsed.sessionStorageOrigins.map((o) => ({ ...o }))
      : Array.isArray(parsed.session_storage_origins)
        ? parsed.session_storage_origins.map((o) => ({ ...o }))
        : [],
  }
  return { ok: true, doc: normalized, summary: summarizeStorageState(normalized) }
}

/** 展平为可编辑表格行（保留 Playwright Cookie 扩展字段到 _extra，避免再保存丢失） */
export function flattenStorageStateForEdit(doc) {
  const d = doc && typeof doc === 'object' ? doc : emptyStorageState()
  const cookies = (Array.isArray(d.cookies) ? d.cookies : []).map((c) => {
    const known = {
      name: String(c?.name || ''),
      value: String(c?.value ?? ''),
      domain: String(c?.domain || ''),
      path: String(c?.path || '/') || '/',
      url: String(c?.url || ''),
      expires: c?.expires != null && c?.expires !== '' ? String(c.expires) : '',
    }
    const extra = {}
    if (c && typeof c === 'object') {
      for (const [k, v] of Object.entries(c)) {
        if (['name', 'value', 'domain', 'path', 'url', 'expires'].includes(k)) continue
        extra[k] = v
      }
    }
    return { ...known, _extra: extra }
  })

  const localRows = []
  for (const o of Array.isArray(d.origins) ? d.origins : []) {
    const origin = String(o?.origin || '').trim()
    const items = Array.isArray(o?.localStorage)
      ? o.localStorage
      : Array.isArray(o?.local_storage)
        ? o.local_storage
        : []
    for (const ent of items) {
      localRows.push({
        origin,
        name: String(ent?.name || ent?.key || ''),
        value: String(ent?.value ?? ''),
      })
    }
  }

  const sessionRows = []
  const ssList = Array.isArray(d.sessionStorageOrigins)
    ? d.sessionStorageOrigins
    : Array.isArray(d.session_storage_origins)
      ? d.session_storage_origins
      : []
  for (const o of ssList) {
    const origin = String(o?.origin || '').trim()
    const items = Array.isArray(o?.sessionStorage)
      ? o.sessionStorage
      : Array.isArray(o?.session_storage)
        ? o.session_storage
        : []
    for (const ent of items) {
      sessionRows.push({
        origin,
        name: String(ent?.name || ent?.key || ''),
        value: String(ent?.value ?? ''),
      })
    }
  }

  return {
    cookies: cookies.length
      ? cookies
      : [{ name: '', value: '', domain: '', path: '/', url: '', expires: '', _extra: {} }],
    localRows: localRows.length ? localRows : [{ origin: '', name: '', value: '' }],
    sessionRows: sessionRows.length ? sessionRows : [{ origin: '', name: '', value: '' }],
  }
}

/** 从表格行重建 storage_state 对象 */
export function buildStorageStateFromEdit({ cookies = [], localRows = [], sessionRows = [] } = {}) {
  const ck = []
  for (const row of cookies) {
    const name = String(row?.name || '').trim()
    if (!name) continue
    const entry = {
      ...(row?._extra && typeof row._extra === 'object' ? row._extra : {}),
      name,
      value: String(row?.value ?? ''),
      path: String(row?.path || '/').trim() || '/',
    }
    const domain = String(row?.domain || '').trim()
    const url = String(row?.url || '').trim()
    if (domain) entry.domain = domain
    else delete entry.domain
    if (url) entry.url = url
    else delete entry.url
    const exp = String(row?.expires ?? '').trim()
    if (exp !== '' && !Number.isNaN(Number(exp))) {
      entry.expires = Number(exp)
    } else if ('expires' in entry && exp === '') {
      // 表格清空 expires 时保留会话 Cookie 语义
      delete entry.expires
    }
    ck.push(entry)
  }

  const lsMap = new Map()
  for (const row of localRows) {
    const origin = String(row?.origin || '').trim()
    const name = String(row?.name || '').trim()
    if (!origin || !name) continue
    if (!lsMap.has(origin)) lsMap.set(origin, [])
    lsMap.get(origin).push({ name, value: String(row?.value ?? '') })
  }

  const ssMap = new Map()
  for (const row of sessionRows) {
    const origin = String(row?.origin || '').trim()
    const name = String(row?.name || '').trim()
    if (!origin || !name) continue
    if (!ssMap.has(origin)) ssMap.set(origin, [])
    ssMap.get(origin).push({ name, value: String(row?.value ?? '') })
  }

  const doc = {
    cookies: ck,
    origins: [...lsMap.entries()].map(([origin, localStorage]) => ({ origin, localStorage })),
  }
  const ssOrigins = [...ssMap.entries()].map(([origin, sessionStorage]) => ({
    origin,
    sessionStorage,
  }))
  if (ssOrigins.length) {
    doc.sessionStorageOrigins = ssOrigins
  }
  return doc
}

export function downloadJsonFile(filename, data) {
  const text = typeof data === 'string' ? data : JSON.stringify(data, null, 2)
  const blob = new Blob([text], { type: 'application/json;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename || 'storage_state.json'
  a.click()
  URL.revokeObjectURL(url)
}

export function readJsonFile(file) {
  return new Promise((resolve, reject) => {
    if (!file) {
      reject(new Error('未选择文件'))
      return
    }
    const reader = new FileReader()
    reader.onload = () => {
      const parsed = parseStorageStateText(String(reader.result || ''))
      if (!parsed.ok) {
        reject(new Error(parsed.error))
        return
      }
      resolve(parsed)
    }
    reader.onerror = () => reject(new Error('读取文件失败'))
    reader.readAsText(file, 'utf-8')
  })
}
