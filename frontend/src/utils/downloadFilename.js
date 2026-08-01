/**
 * 从 Content-Disposition 解析下载文件名；兼容 filename* / filename。
 */
export function filenameFromContentDisposition(header) {
  if (!header || typeof header !== 'string') return ''
  const star = /filename\*\s*=\s*(?:UTF-8''|utf-8'')([^;]+)/i.exec(header)
  if (star?.[1]) {
    try {
      return decodeURIComponent(star[1].trim().replace(/^"|"$/g, ''))
    } catch {
      return star[1].trim().replace(/^"|"$/g, '')
    }
  }
  const plain = /filename\s*=\s*("?)([^";]+)\1/i.exec(header)
  return plain?.[2]?.trim() || ''
}

/** 去掉路径非法字符，生成安全下载名。 */
export function sanitizeDownloadBasename(name, fallback = 'report', maxLen = 80) {
  let s = String(name || '')
    .trim()
    .replace(/[\\/:*?"<>|\r\n\t]+/g, '_')
    .replace(/\s+/g, ' ')
    .replace(/^[.\s_]+|[.\s_]+$/g, '')
  if (!s) s = fallback
  if (s.length > maxLen) s = s.slice(0, maxLen).replace(/[.\s_]+$/g, '')
  return s || fallback
}

/**
 * 优先用响应头文件名，否则用 title + 后缀。
 * @param {import('axios').AxiosResponse} res
 * @param {{ title?: string, fallback?: string, ext?: string }} opts
 */
export function resolveDownloadFilename(res, opts = {}) {
  const ext = opts.ext || '.html'
  const fromHeader = filenameFromContentDisposition(
    res?.headers?.['content-disposition'] || res?.headers?.['Content-Disposition']
  )
  if (fromHeader) return fromHeader
  const base = sanitizeDownloadBasename(opts.title || opts.fallback || 'report')
  return base.toLowerCase().endsWith(ext.toLowerCase()) ? base : `${base}${ext}`
}
