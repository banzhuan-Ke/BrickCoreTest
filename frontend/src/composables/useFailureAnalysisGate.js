import { ref, computed, unref, onMounted, watch } from 'vue'
import { aiConfigApi } from '@/api/modules/ai.js'
import { UserStore } from '@/stores/module/UserStore.js'
import { ProjectStore } from '@/stores/module/ProjectStore.js'

/** 主动分析入口：只看项目总开关（小测 / 用例编辑 / 执行记录列表） */
export function evaluateFailureAnalysisActive(execSettings, hasPermission) {
  if (!hasPermission) return false
  if (!execSettings) return false
  return execSettings.failure_analysis_enabled !== false
}

/** 纯函数：报告页是否展示失败 AI 分析入口（W-16，可结合执行 env 快照） */
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

/**
 * @param {import('vue').Ref|null} runInfoRef 报告页传入 run/env；主动入口可传 null
 * @param {{ syncProject?: boolean }} options
 */
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

  const hasAiPerm = () => uStore.hasPermission('ai_test:execute')

  /** 报告页入口：尊重执行 env / 报告默认展示 */
  const canShowFailureAnalysis = computed(() =>
    evaluateFailureAnalysisVisibility(
      execSettings.value,
      unref(runInfoRef)?.env,
      hasAiPerm(),
    ),
  )

  /** 主动分析：仅项目「启用失败 AI 分析」 */
  const canActiveAnalyze = computed(() =>
    evaluateFailureAnalysisActive(execSettings.value, hasAiPerm()),
  )

  function canAnalyzeExecution(row, fallbackEnv) {
    const env = row?.env ?? fallbackEnv ?? unref(runInfoRef)?.env
    return evaluateFailureAnalysisVisibility(
      execSettings.value,
      env,
      hasAiPerm(),
    )
  }

  return {
    execSettings,
    loadExecSettings,
    canShowFailureAnalysis,
    canActiveAnalyze,
    canAnalyzeExecution,
  }
}
