/**
 * Web 用例描述：录制 / AI 优化共用（方案 C：单字段 description）
 */

/** 打开录制或 AI 优化时，解析用例描述上下文 */
export function resolveCaseDescriptionForContext(caseInfo) {
  const desc = (caseInfo?.description || '').trim()
  if (desc) return desc.slice(0, 4000)
  const name = (caseInfo?.name || '').trim()
  if (name) return `【用例】${name}`.slice(0, 4000)
  return ''
}

/** 从步骤中提取首个 open_url，供录制起始页预填 */
export function extractOpenUrlFromSteps(steps) {
  const list = steps || []
  const hit = list.find((s) => s?.method === 'open_url' && s?.params?.url)
  return (hit?.params?.url || '').trim()
}

/** 兼容录制 apply 事件：旧版仅 steps 数组，新版 { steps, description } */
export function normalizeRecorderApplyPayload(payload) {
  if (Array.isArray(payload)) {
    return { steps: payload, description: '' }
  }
  return {
    steps: Array.isArray(payload?.steps) ? payload.steps : [],
    description: (payload?.description || '').trim(),
  }
}
