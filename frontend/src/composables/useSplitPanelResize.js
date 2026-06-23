import { ref, onMounted } from 'vue'

/**
 * 水平分栏拖拽调整宽度（用于套件编辑页中间/右侧）
 */
export function useSplitPanelResize(options = {}) {
  const {
    storageKey = 'suite-edit-right-panel-width',
    defaultWidth = 560,
    minWidth = 380,
    maxWidth = 960,
  } = options

  const rightWidth = ref(defaultWidth)
  const isResizing = ref(false)

  onMounted(() => {
    try {
      const saved = localStorage.getItem(storageKey)
      if (!saved) return
      const parsed = parseInt(saved, 10)
      if (!Number.isNaN(parsed)) {
        rightWidth.value = Math.min(maxWidth, Math.max(minWidth, parsed))
      }
    } catch {
      // ignore
    }
  })

  function onResizeStart(event) {
    event.preventDefault()
    isResizing.value = true
    const startX = event.clientX
    const startWidth = rightWidth.value

    function onMove(ev) {
      const delta = startX - ev.clientX
      rightWidth.value = Math.min(maxWidth, Math.max(minWidth, startWidth + delta))
    }

    function onUp() {
      isResizing.value = false
      try {
        localStorage.setItem(storageKey, String(rightWidth.value))
      } catch {
        // ignore
      }
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }

    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }

  return { rightWidth, isResizing, onResizeStart }
}
