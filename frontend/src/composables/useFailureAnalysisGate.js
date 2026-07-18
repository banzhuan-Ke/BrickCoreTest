import { ref, computed, unref, onMounted, watch } from 'vue'
import { aiConfigApi } from '@/api/modules/ai.js'
import { UserStore } from '@/stores/module/UserStore.js'
import { ProjectStore } from '@/stores/module/ProjectStore.js'

/** 纯函数：是否展示失败 AI 分析入口（W-16） */
export function evaluateFailureAnalysisVisibility(execSettings, env, hasPermission) {
  if (!hasPermission) return false
  // 配置未加载前默认隐藏，避免误放行
  if (!execSettings) return false
  if (execSettings.failure_analysis_enabled === false) return false
  const envFlag = env?.failure_analysis_on_report
  if (envFlag === false) return false
  if (envFlag === true) return true
  return execSettings.failure_analysis_default_on_report !== false
}

/** 监听项目切换并加载执行设置 */
export function syncFailureAnalysisWithProject(loadExecSettings) {
  const proStore = ProjectStore()
  onMounted(() => {
    loadExecSettings(proStore.projectInfo?.id)
  })
  watch(
    () => proStore.projectInfo?.id,
    (pid) => loadExecSettings(pid),
  )
}

/** 报告页是否展示失败 AI 分析入口（W-16） */
export function useFailureAnalysisGate(runInfoRef, { syncProject = false } = {}) {
  const execSettings = ref(null)
  const uStore = UserStore()

  async function loadExecSettings(projectId) {
    if (!projectId) {
      execSettings.value = null
      return
    }
    try {
      const res = await aiConfigApi.getExecutionSettings(projectId)
      if (res.data?.code === 200) {
        execSettings.value = res.data.data || null
      }
    } catch {
      execSettings.value = null
    }
  }

  if (syncProject) {
    syncFailureAnalysisWithProject(loadExecSettings)
  }

  const canShowFailureAnalysis = computed(() =>
    evaluateFailureAnalysisVisibility(
      execSettings.value,
      unref(runInfoRef)?.env,
      uStore.hasPermission('ai_test:execute'),
    ),
  )

  function canAnalyzeExecution(row, fallbackEnv) {
    const env = row?.env ?? fallbackEnv ?? unref(runInfoRef)?.env
    return evaluateFailureAnalysisVisibility(
      execSettings.value,
      env,
      uStore.hasPermission('ai_test:execute'),
    )
  }

  return { execSettings, loadExecSettings, canShowFailureAnalysis, canAnalyzeExecution }
}
