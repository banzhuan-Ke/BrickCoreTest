import { computed, ref, watch } from 'vue'

const STORAGE_KEY = 'catalogSidebarCollapsed'

function readCollapsed() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw === null || raw === undefined || raw === '') return true
    return raw === '1' || raw === 'true'
  } catch {
    return true
  }
}

/** 全局共享：各列表页测试目录侧栏收起状态（默认收起） */
const collapsed = ref(readCollapsed())

watch(collapsed, (v) => {
  try {
    localStorage.setItem(STORAGE_KEY, v ? '1' : '0')
  } catch {
    // ignore
  }
})

export function useCatalogSidebarCollapse() {
  const isCollapsed = computed(() => collapsed.value)
  const toggle = () => {
    collapsed.value = !collapsed.value
  }
  const expand = () => {
    collapsed.value = false
  }
  const collapse = () => {
    collapsed.value = true
  }
  return { isCollapsed, collapsed, toggle, expand, collapse }
}
