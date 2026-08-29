/**
 * UI Agent Job 轮询 + 实时展示（GET 任务详情，1.5s 间隔）。
 */
import { onBeforeUnmount, ref } from 'vue'
import { aiGenerateApi } from '@/api/modules/ai'
import { shouldPresentUiAgentSteps } from '@/views/AI/components/uiAgentJobHelpers.js'

export function useUiAgentJobPoll(options = {}) {
  const pollIntervalMs = options.pollIntervalMs ?? 1500

  const displayedLogs = ref([])
  const displayedSteps = ref([])
  const jobStatus = ref('')
  const jobData = ref(null)
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
    displayedLogs.value = []
    displayedSteps.value = []
    jobStatus.value = ''
    jobData.value = null
    errorMessage.value = ''
  }

  function syncFromJob(job) {
    displayedLogs.value = [...(job.agent_log || [])]
    displayedSteps.value = [...(job.steps || [])]
  }

  async function pollOnce(jobId, projectId) {
    const res = await aiGenerateApi.getUiAgentJob(jobId, projectId)
    const job = res.data?.data || res.data
    if (!job) {
      throw new Error('任务不存在')
    }
    jobData.value = job
    jobStatus.value = job.status
    syncFromJob(job)
    return job
  }

  function start(jobId, projectId, callbacks = {}) {
    reset()
    if (!jobId) return

    const tick = async () => {
      if (pollInFlight) return
      pollInFlight = true
      try {
        const job = await pollOnce(jobId, projectId)
        if (['done', 'failed', 'stopped'].includes(job.status)) {
          syncFromJob(job)
          stop()
          if (shouldPresentUiAgentSteps(job)) {
            callbacks.onDone?.(job)
          } else {
            callbacks.onFail?.({
              error_message: job.error_message || 'Agent 失败',
              job,
            })
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
    displayedLogs,
    displayedSteps,
    jobStatus,
    jobData,
    errorMessage,
    start,
    stop,
    reset,
    pollOnce,
  }
}
