/** 项目成员 id → 展示名 */
import http from '@/api/index'

/**
 * @param {number} projectId
 * @returns {Promise<Map<number, string>>}
 */
export async function loadMemberNameMap(projectId) {
  const map = new Map()
  if (!projectId) return map
  try {
    const res = await http.projectApi.getMembers(projectId, { page: 1, size: 200 })
    const items = res.data?.data?.items || res.data?.data || []
    for (const m of items) {
      const id = Number(m.user_id)
      if (!id) continue
      const name = m.nickname || m.username || `用户 ${id}`
      map.set(id, name)
      if (m.username) map.set(`u:${m.username}`, name)
    }
  } catch {
    // 列表展示降级为 ID
  }
  return map
}

/** @param {number|null|undefined} userId @param {Map<number, string>} nameMap */
export function formatMemberName(userId, nameMap) {
  if (userId == null || userId === '') return '—'
  const id = Number(userId)
  const name = nameMap?.get(id)
  return name ? `${name}` : `#${id}`
}

/** @param {number[]|null|undefined} ids @param {Map<number, string>} nameMap */
export function formatMemberNames(ids, nameMap) {
  if (!ids?.length) return '—'
  return ids.map((id) => formatMemberName(id, nameMap)).join('、')
}

/** @param {string|null|undefined} username @param {Map<number|string, string>} nameMap */
export function formatMemberByUsername(username, nameMap) {
  if (!username) return '—'
  const key = `u:${username}`
  return nameMap?.get(key) || username
}

/** 豁免剩余天数文案；无效则返回空串 */
export function waiverRemainingLabel(snapshot, maxDays = 14) {
  if (!snapshot || snapshot.conclusion !== 'conditional_pass') return ''
  if (snapshot.waiver_valid === false) return '已过期'
  const raw = snapshot.waiver_approved_at || snapshot.create_time
  if (!raw) return snapshot.waiver_valid ? '有效' : ''
  const at = new Date(raw)
  if (Number.isNaN(at.getTime())) return ''
  const end = at.getTime() + maxDays * 24 * 3600 * 1000
  const leftMs = end - Date.now()
  if (leftMs <= 0) return '已过期'
  const days = Math.ceil(leftMs / (24 * 3600 * 1000))
  return `剩余约 ${days} 天`
}
