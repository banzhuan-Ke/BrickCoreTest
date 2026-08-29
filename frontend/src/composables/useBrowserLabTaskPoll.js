/**
 * Browser Lab 任务轮询 + 实时展示（GET 任务详情，1.5s 间隔）。
 */
import { onBeforeUnmount, ref } from 'vue'
import { browserLabApi } from '@/api/modules/ai'

export function useBrowserLabTaskPoll(options = {}) {
  const pollIntervalMs = options.pollIntervalMs ?? 1500

  const displayedSteps = ref([])
  const taskStatus = ref('')
  const taskData = ref(null)
  const errorMessage = ref('')

  let pollTimer = null
  let pollInFlight = false

  function stop() {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  function reset() {
    stop()
    displayedSteps.value = []
    taskStatus.value = ''
    taskData.value = null
    errorMessage.value = ''
  }

  /** 展示用步骤：有 Agent 步时隐藏 bootstrap(Step 0) */
  function normalizeBrowserLabStepsForPoll(stepLog) {
    const raw = (stepLog || []).filter((e) => e?.type === 'step')
    const agent = raw.filter((e) => Number(e.index) !== 0 && e.step_status !== 'bootstrap')
    const bootstrap = raw.filter((e) => Number(e.index) === 0 || e.step_status === 'bootstrap')
    const list = agent.length ? agent : bootstrap
    return [...list].sort((a, b) => Number(a.index || 0) - Number(b.index || 0))
  }

  function syncStepsFromLog(stepLog) {
    displayedSteps.value = normalizeBrowserLabStepsForPoll(stepLog)
  }

  function buildDoneEvent(task) {
    const log = task.step_log || []
    let evt = null
    for (let i = log.length - 1; i >= 0; i -= 1) {
      const item = log[i]
      if (item?.type === 'done') {
        evt = item
        break
      }
    }
    const tokensUsed = Number(task.tokens_used || evt?.tokens_used || 0)
    if (evt) {
      return {
        ...evt,
        type: 'done',
        status: task.status || evt.status,
        summary: task.result_summary || evt.summary || '',
        error_message: task.error_message || evt.error_message || '',
        tokens_used: tokensUsed,
        gif_url: task.gif_url || evt.gif_url || '',
        gif_path: task.gif_path || evt.gif_path || '',
      }
    }
    return {
      type: 'done',
      status: task.status,
      summary: task.result_summary || '',
      error_message: task.error_message || '',
      tokens_used: tokensUsed,
      gif_url: task.gif_url || '',
      gif_path: task.gif_path || '',
    }
  }

  async function pollOnce(taskId, projectId) {
    const res = await browserLabApi.getTask(taskId, projectId)
    const task = res.data?.data || res.data
    if (!task) {
      throw new Error('任务不存在')
    }
    taskData.value = task
    taskStatus.value = task.status
    syncStepsFromLog(task.step_log || [])
    return task
  }

  function start(taskId, projectId, callbacks = {}) {
    reset()
    if (!taskId) return

    const tick = async () => {
      if (pollInFlight) return
      pollInFlight = true
      try {
        const task = await pollOnce(taskId, projectId)
        if (['done', 'failed', 'stopped'].includes(task.status)) {
          syncStepsFromLog(task.step_log || [])
          stop()
          if (task.status === 'failed') {
            callbacks.onFail?.({
              error_message: task.error_message || task.result_summary || '执行失败',
              task,
            })
          } else {
            callbacks.onDone?.(buildDoneEvent(task), task)
          }
        }
      } catch (e) {
        stop()
        errorMessage.value = e.response?.data?.detail || e.message || '轮询失败'
        callbacks.onFail?.({ error_message: errorMessage.value })
      } finally {
        pollInFlight = false
      }
    }

    tick()
    pollTimer = setInterval(tick, pollIntervalMs)
  }

  onBeforeUnmount(stop)

  return {
    displayedSteps,
    taskStatus,
    taskData,
    errorMessage,
    start,
    stop,
    reset,
    pollOnce,
  }
}
