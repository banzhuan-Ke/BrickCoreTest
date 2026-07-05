/** App 图像模板 object_key → 预签名预览 URL */
import { appElementApi } from '@/api/modules/app.js'

export function isTemplateObjectKey(value) {
  const v = String(value || '').trim()
  return !!v && !v.startsWith('http')
}

export async function presignTemplateKeys(keys, projectId) {
  const unique = [...new Set((keys || []).filter(isTemplateObjectKey))]
  if (!unique.length || !projectId) return {}
  try {
    const res = await appElementApi.presignTemplates(projectId, unique)
    return res.data?.data || res.data || {}
  } catch {
    return {}
  }
}

export function resolveTemplatePreviewUrl(value, urlMap = {}) {
  const v = String(value || '').trim()
  if (!v) return ''
  if (v.startsWith('http')) return v
  return urlMap[v] || ''
}
