import http from '../request'

export const runnerReleaseApi = {
  getRelease() {
    return http.get('/runner/client-release')
  },
  getConfig() {
    return http.get('/sys/runner-release/config')
  },
  updateConfig(data) {
    return http.put('/sys/runner-release/config', data)
  },
  downloadUrl(token) {
    const base = (import.meta.env.VITE_BASE_API || '').replace(/\/$/, '')
    const path = `${base}/runner/client-download`
    if (!token) return path
    const sep = path.includes('?') ? '&' : '?'
    return `${path}${sep}access_token=${encodeURIComponent(token)}`
  },
}
