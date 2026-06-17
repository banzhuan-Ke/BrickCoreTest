import { ref, computed, watch } from 'vue'
import {
  getTableColumnPageConfig,
  getDefaultColumnState
} from '@/config/tableColumnRegistry.js'
import { UserStore } from '@/stores/module/UserStore.js'

function storageKey(pageId, userId) {
  return `table_cols:v1:${pageId}:${userId || 'anon'}`
}

function loadSavedState(pageId, userId) {
  const cfg = getTableColumnPageConfig(pageId)
  if (!cfg) return null
  const defaults = getDefaultColumnState(pageId)
  try {
    const raw = localStorage.getItem(storageKey(pageId, userId))
    if (!raw) return defaults
    const parsed = JSON.parse(raw)
    if (!parsed || !Array.isArray(parsed.order) || !Array.isArray(parsed.visible)) {
      return defaults
    }
    const validKeys = new Set(cfg.columns.map(c => c.key))
    let order = parsed.order.filter(k => validKeys.has(k))
    let visible = parsed.visible.filter(k => validKeys.has(k))
    cfg.columns.forEach(c => {
      if (!order.includes(c.key)) order.push(c.key)
    })
    if (parsed.version < cfg.version) {
      const visibleSet = new Set(visible)
      cfg.defaultVisible.forEach(k => {
        if (!visibleSet.has(k) && validKeys.has(k)) {
          visible.push(k)
          visibleSet.add(k)
        }
      })
    }
    cfg.columns.filter(c => c.required).forEach(c => {
      if (!visible.includes(c.key)) visible.unshift(c.key)
      if (!order.includes(c.key)) order.unshift(c.key)
    })
    visible = [...new Set(visible)]
    return { version: cfg.version, order, visible }
  } catch {
    return defaults
  }
}

function saveState(pageId, userId, state) {
  localStorage.setItem(storageKey(pageId, userId), JSON.stringify(state))
}

/**
 * 列表页列显示/顺序配置
 * @param {string} pageId - tableColumnRegistry 中的 pageId
 */
export function useTableColumns(pageId) {
  const uStore = UserStore()
  const pageConfig = getTableColumnPageConfig(pageId)
  if (!pageConfig) {
    console.warn(`[useTableColumns] unknown pageId: ${pageId}`)
  }

  const userId = computed(() => uStore.userInfo?.id || uStore.userInfo?.username || 'anon')

  const columnMap = computed(() => {
    const map = {}
    for (const c of pageConfig?.columns || []) map[c.key] = c
    return map
  })

  const state = ref(loadSavedState(pageId, userId.value))

  watch(userId, (id) => {
    state.value = loadSavedState(pageId, id)
  })

  watch(
    state,
    (val) => {
      if (pageConfig) saveState(pageId, userId.value, val)
    },
    { deep: true }
  )

  const activeColumns = computed(() => {
    const visibleSet = new Set(state.value.visible)
    return state.value.order
      .filter(k => visibleSet.has(k) && columnMap.value[k])
      .map(k => columnMap.value[k])
  })

  const pickerItems = computed(() =>
    state.value.order
      .filter(k => columnMap.value[k])
      .map(k => ({
        ...columnMap.value[k],
        visible: state.value.visible.includes(k)
      }))
  )

  const tableRenderKey = computed(() =>
    `${pageId}:${state.value.order.join(',')}:${state.value.visible.join(',')}`
  )

  function isColumnVisible(key) {
    return state.value.visible.includes(key)
  }

  function setColumnVisible(key, visible) {
    const col = columnMap.value[key]
    if (!col || col.required) return
    const set = new Set(state.value.visible)
    if (visible) set.add(key)
    else set.delete(key)
    state.value.visible = state.value.order.filter(k => set.has(k))
  }

  function setPickerOrder(orderedKeys) {
    const valid = new Set(pageConfig?.columns.map(c => c.key) || [])
    const next = orderedKeys.filter(k => valid.has(k))
    pageConfig?.columns.forEach(c => {
      if (!next.includes(c.key)) next.push(c.key)
    })
    state.value.order = next
    const visibleSet = new Set(state.value.visible)
    state.value.visible = next.filter(k => visibleSet.has(k))
  }

  function resetColumns() {
    state.value = getDefaultColumnState(pageId)
  }

  return {
    pageConfig,
    state,
    activeColumns,
    pickerItems,
    tableRenderKey,
    isColumnVisible,
    setColumnVisible,
    setPickerOrder,
    resetColumns
  }
}
