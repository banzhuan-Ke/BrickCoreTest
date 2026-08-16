import http from '../request'

export const runnerReleaseApi = {
  getRelease() {
    return http.get('/runner/client-release')
  },
  getConfig() {
    return http.get('/sys/runner-release/config', { timeout: 60000 })
  },
  updateConfig(data) {
    return http.put('/sys/runner-release/config', data, { timeout: 60000 })
  },
  downloadUrl(token) {
    const base = (import.meta.env.VITE_BASE_API || '').replace(/\/$/, '')
    const path = `${base}/runner/client-download`
    if (!token) return path
    const sep = path.includes('?') ? '&' : '?'
    return `${path}${sep}access_token=${encodeURIComponent(token)}`
  },
  /** @param {'win'|'mac'} platform */
  perfDownloadUrl(token, platform = 'win') {
    const base = (import.meta.env.VITE_BASE_API || '').replace(/\/$/, '')
    const plat = platform === 'mac' ? 'mac' : 'win'
    let path = `${base}/runner/perf-client-download?platform=${plat}`
    if (!token) return path
    return `${path}&access_token=${encodeURIComponent(token)}`
  },
}
