import { onUnmounted, watch } from 'vue'

export const UI_EXECUTION_ACTIVE_STATUSES = Object.freeze([
  '执行中',
  '等待执行',
  'running',
  'pending',
])

export function isUiExecutionActive(status) {
  return UI_EXECUTION_ACTIVE_STATUSES.includes(status)
}

/**
 * 计算 UI 计划/套件执行进度。
 * 优先用 run_all；否则用 success+fail+error+skip。
 */
export function uiExecutionProgress(row) {
  const total = Math.max(0, Number(row?.case_count) || 0)
  const runAll = Number(row?.run_all)
  const accounted =
    Number.isFinite(runAll) && runAll >= 0
      ? runAll
      : (Number(row?.success) || 0) +
        (Number(row?.fail) || 0) +
        (Number(row?.error) || 0) +
        (Number(row?.skip) || 0)
  const done = Math.max(0, Math.min(total || accounted, accounted))
  const percent = total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0
  return { total, done, percent }
}

/**
 * 列表/报告在「执行中」时自动轮询刷新。
 * @param {() => Promise<void>|void} refreshFn
 * @param {() => boolean} hasActiveFn 返回当前视图是否仍有进行中记录
 * @param {{ intervalMs?: number }} options
 */
export function useUiExecutionProgressPoll(refreshFn, hasActiveFn, options = {}) {
  const intervalMs = options.intervalMs ?? 3000
  let timer = null
  let inFlight = false

  const stopPoll = () => {
    if (timer != null) {
      clearInterval(timer)
      timer = null
    }
  }

  const tick = async () => {
    if (inFlight) return
    if (typeof hasActiveFn === 'function' && !hasActiveFn()) {
      stopPoll()
      return
    }
    inFlight = true
    try {
      await refreshFn()
    } catch {
      // 轮询失败不打断页面；下一轮再试
    } finally {
      inFlight = false
      if (typeof hasActiveFn === 'function' && !hasActiveFn()) {
        stopPoll()
      }
    }
  }

  const startPoll = () => {
    stopPoll()
    if (typeof hasActiveFn === 'function' && !hasActiveFn()) return
    timer = setInterval(tick, intervalMs)
  }

  const syncPoll = () => {
    if (typeof hasActiveFn === 'function' && hasActiveFn()) startPoll()
    else stopPoll()
  }

  onUnmounted(stopPoll)

  return { startPoll, stopPoll, syncPoll }
}

/** 列表数据变化后同步轮询开关 */
export function watchUiExecutionListForPoll(listRef, syncPoll) {
  watch(
    listRef,
    () => {
      syncPoll()
    },
    { deep: false }
  )
}
