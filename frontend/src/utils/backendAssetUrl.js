/**
 * 将后端返回的相对静态路径拼成可访问 URL。
 * 本地非 Docker：前端 :8080、Backend :8000，相对 /static/... 会打到前端导致白页。
 */
export function resolveBackendAssetUrl(pathOrUrl) {
  const raw = (pathOrUrl || '').trim()
  if (!raw) return ''
  if (/^https?:\/\//i.test(raw) || raw.startsWith('blob:') || raw.startsWith('data:')) {
    return raw
  }
  const base = (import.meta.env.VITE_BASE_API || '').replace(/\/$/, '')
  const path = raw.startsWith('/') ? raw : `/${raw}`
  return `${base}${path}`
}

/** 触发浏览器下载（跨端口时用完整 Backend URL） */
export function triggerBackendFileDownload(pathOrUrl, filename) {
  const href = resolveBackendAssetUrl(pathOrUrl)
  if (!href) return false
  const link = document.createElement('a')
  link.href = href
  if (filename) link.download = filename
  link.target = '_blank'
  link.rel = 'noopener'
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  return true
}
