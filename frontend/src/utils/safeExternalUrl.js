/** 仅允许 http/https 外链，防 javascript: 等 XSS */
export function safeExternalUrl(url) {
  const raw = String(url || '').trim()
  if (!raw) return ''
  try {
    const parsed = new URL(raw, typeof window !== 'undefined' ? window.location.origin : 'https://local.invalid')
    if (parsed.protocol === 'http:' || parsed.protocol === 'https:') {
      return parsed.href
    }
  } catch {
    return ''
  }
  return ''
}
