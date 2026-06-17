import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { assetFavoriteApi } from '@/api/modules/sys'
import { ProjectStore } from '@/stores/module/ProjectStore'

/** 按 assetType + projectId 隔离，避免接口页与 Web 用例页互相污染 */
const favoriteCache = new Map()

function cacheKey(assetType, projectId) {
  return `${assetType}:${projectId}`
}

export function useAssetFavorites(assetType) {
  const proStore = ProjectStore()
  const projectId = computed(() => proStore.projectInfo?.id)
  /** 响应式版本号，toggle 后递增以触发依赖它的组件重渲染 */
  const favoriteRevision = ref(0)
  let loading = false

  function getSet(projectIdVal) {
    if (!projectIdVal) return new Set()
    return favoriteCache.get(cacheKey(assetType, projectIdVal)) || new Set()
  }

  function setSet(projectIdVal, set) {
    if (!projectIdVal) return
    favoriteCache.set(cacheKey(assetType, projectIdVal), new Set(set))
  }

  async function loadFavorites(force = false) {
    const pid = projectId.value
    if (!pid) return
    const key = cacheKey(assetType, pid)
    if (!force && favoriteCache.has(key)) return
    if (loading) return
    loading = true
    try {
      const res = await assetFavoriteApi.list(pid)
      const items = res.data?.data || []
      const next = new Set()
      items.forEach((item) => {
        if (item.asset_type === assetType) {
          next.add(item.asset_id)
        }
      })
      favoriteCache.set(key, next)
      favoriteRevision.value += 1
    } finally {
      loading = false
    }
  }

  function isFavorite(assetId) {
    // 读取 revision 建立响应式依赖
    void favoriteRevision.value
    return getSet(projectId.value).has(assetId)
  }

  async function toggleFavorite(assetId) {
    const pid = projectId.value
    if (!pid || !assetId) return
    const current = new Set(getSet(pid))
    try {
      if (current.has(assetId)) {
        await assetFavoriteApi.remove(pid, assetType, assetId)
        current.delete(assetId)
        ElMessage.success('已取消收藏')
      } else {
        await assetFavoriteApi.add(pid, { asset_type: assetType, asset_id: assetId })
        current.add(assetId)
        ElMessage.success('已收藏')
      }
      setSet(pid, current)
      favoriteRevision.value += 1
    } catch (e) {
      ElMessage.error(e?.response?.data?.detail || e?.data?.detail || '操作失败')
    }
  }

  function sortByFavorites(list, idKey = 'id') {
    void favoriteRevision.value
    const fav = getSet(projectId.value)
    return [...(list || [])].sort((a, b) => {
      const af = fav.has(a[idKey]) ? 0 : 1
      const bf = fav.has(b[idKey]) ? 0 : 1
      if (af !== bf) return af - bf
      return (b[idKey] || 0) - (a[idKey] || 0)
    })
  }

  return {
    loadFavorites,
    isFavorite,
    toggleFavorite,
    sortByFavorites,
    favoriteRevision,
  }
}
