/**
 * Web 用例描述：录制 / AI 优化共用（方案 C：单字段 description）
 */

import { flattenGlobalVars } from './globalVars.js'

const VAR_PATTERN = /\$\{\{([^}]+)\}\}/g

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

/** 环境 global_vars 中 Web 默认起始 URL 的保留键 */
export const ENV_DEFAULT_START_URL_KEY = '__default_start_url'

export function getEnvDefaultStartUrl(globalVars) {
  const gv = globalVars && typeof globalVars === 'object' ? globalVars : {}
  const raw = gv[ENV_DEFAULT_START_URL_KEY]
  if (raw && typeof raw === 'object' && 'value' in raw) {
    return String(raw.value || '').trim()
  }
  return String(raw || '').trim()
}

export function getProjectDefaultStartUrl(projectInfo) {
  const ai = projectInfo?.global_vars?.ai_settings
  return String(ai?.default_start_url || '').trim()
}

export function containsUnresolvedTemplate(text) {
  const s = String(text || '')
  return s.includes('${{') || s.includes('${')
}

export function substituteVariablesInText(text, variables) {
  const raw = String(text || '')
  if (!raw || !raw.includes('${{')) return raw
  const vars = variables && typeof variables === 'object' ? variables : {}
  return raw.replace(VAR_PATTERN, (match, key) => {
    const k = String(key || '').trim()
    if (Object.prototype.hasOwnProperty.call(vars, k)) {
      return String(vars[k] ?? '')
    }
    return match
  })
}

/** 构建 URL 变量替换上下文（项目 + 环境 global_vars，与后端 merge 顺序近似） */
export function buildStartUrlVariables(env, projectInfo = null) {
  const vars = {}
  if (projectInfo?.global_vars) {
    Object.assign(vars, flattenGlobalVars(projectInfo.global_vars))
  }
  if (env?.global_vars) {
    Object.assign(vars, flattenGlobalVars(env.global_vars))
  }
  const host = String(env?.host || '').trim()
  if (host) {
    vars.Base_url = host
    if (!vars.host) vars.host = host
  }
  return vars
}

/**
 * 校验 default_start_url 存储值（与后端 start_url.validate_default_start_url 对齐）
 * @returns {{ ok: boolean, error?: string, normalized?: string }}
 */
export function validateDefaultStartUrl(url) {
  const u = String(url || '').trim()
  if (!u) return { ok: true, normalized: '' }
  if (u.length > 500) return { ok: false, error: '默认起始 URL 长度不能超过 500 字符' }
  if (/\s/.test(u)) return { ok: false, error: '默认起始 URL 不能包含空格' }
  if (u.includes('${{')) return { ok: true, normalized: u }
  if (!/^https?:\/\//i.test(u)) {
    return { ok: false, error: '默认起始 URL 须以 http:// 或 https:// 开头，或使用 ${{变量名}} 模板' }
  }
  return { ok: true, normalized: u }
}

function resolveRawDefaultStartUrl({ steps, envId = null, envList = [], projectInfo = null } = {}) {
  const fromSteps = extractOpenUrlFromSteps(steps)
  if (fromSteps) return { raw: fromSteps, env: null }

  const env = envId != null
    ? (envList || []).find((e) => e.id === envId)
    : (envList || [])[0] || null
  const fromEnv = env ? getEnvDefaultStartUrl(env.global_vars) : ''
  if (fromEnv) return { raw: fromEnv, env }

  const fromProject = getProjectDefaultStartUrl(projectInfo)
  if (fromProject) return { raw: fromProject, env }

  const host = (env?.host || '').trim()
  if (!host) return { raw: '', env: env }
  const fallback = /^https?:\/\//i.test(host) ? host : `https://${host}`
  return { raw: fallback, env: env }
}

/**
 * 解析 Web 录制/调试默认起始 URL（含 ${{var}} 替换，与后端 debug 行为对齐）
 * envId 为空时使用 envList[0]；不绑定「变量插入参考环境」
 */
export function resolveDefaultStartUrl({
  steps,
  envId = null,
  envList = [],
  projectInfo = null,
  resolveVariables = true,
} = {}) {
  const { raw, env } = resolveRawDefaultStartUrl({ steps, envId, envList, projectInfo })
  if (!raw) return ''
  if (!resolveVariables) return raw

  const variables = buildStartUrlVariables(env, projectInfo)
  const resolved = substituteVariablesInText(raw, variables)
  if (containsUnresolvedTemplate(resolved)) return ''
  return resolved
}

/** 从 global_vars 中剥离保留键，供 GlobalVarsEditor 展示 */
export function globalVarsForEditor(globalVars) {
  const gv = globalVars && typeof globalVars === 'object' ? { ...globalVars } : {}
  delete gv[ENV_DEFAULT_START_URL_KEY]
  return gv
}

/** 合并默认起始 URL 到 global_vars 保存 payload */
export function mergeEnvDefaultStartUrl(globalVars, defaultStartUrl) {
  const check = validateDefaultStartUrl(defaultStartUrl)
  if (!check.ok) {
    throw new Error(check.error || '默认起始 URL 无效')
  }
  const gv = globalVars && typeof globalVars === 'object' ? { ...globalVars } : {}
  const url = check.normalized || ''
  if (url) {
    gv[ENV_DEFAULT_START_URL_KEY] = url
  } else {
    delete gv[ENV_DEFAULT_START_URL_KEY]
  }
  return gv
}

/** 兼容录制 apply 事件：旧版仅 steps 数组，新版 { steps, description, applyMode, insertAtIndex } */
export function normalizeRecorderApplyPayload(payload) {
  if (Array.isArray(payload)) {
    return { steps: payload, description: '', applyMode: 'replace', insertAtIndex: null }
  }
  return {
    steps: Array.isArray(payload?.steps) ? payload.steps : [],
    description: (payload?.description || '').trim(),
    applyMode: payload?.applyMode || 'replace',
    insertAtIndex: payload?.insertAtIndex ?? null,
  }
}
