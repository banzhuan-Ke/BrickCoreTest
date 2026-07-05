const CONTEXT_KEY = 'app_inspector_context'
const RESULT_KEY = 'app_inspector_result'
const DRAFT_KEY = 'app_inspector_case_draft'

/** @typedef {{ returnPath: string, returnName?: string, stepIndex?: number, stepPath?: number[], driverMode?: string, caseId?: string|number, projectId?: string|number }} AppInspectorContext */

function parseJson(raw) {
  try {
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

/** @param {AppInspectorContext} ctx */
export function setAppInspectorContext(ctx) {
  try {
    sessionStorage.setItem(CONTEXT_KEY, JSON.stringify(ctx))
  } catch {
    /* ignore quota */
  }
}

/** @returns {AppInspectorContext | null} */
export function getAppInspectorContext() {
  try {
    return parseJson(sessionStorage.getItem(CONTEXT_KEY))
  } catch {
    return null
  }
}

export function peekAppInspectorContext() {
  return getAppInspectorContext()
}

export function clearAppInspectorContext() {
  try {
    sessionStorage.removeItem(CONTEXT_KEY)
  } catch {
    /* ignore */
  }
}

/** 跳转探查前保存用例编辑草稿，避免返回时被 loadDetail 覆盖 */
export function setAppInspectorCaseDraft(caseInfo, meta = {}) {
  try {
    const payload = {
      ...(caseInfo && typeof caseInfo === 'object' ? caseInfo : {}),
      __meta: {
        caseId: meta.caseId ?? null,
        projectId: meta.projectId ?? null,
        savedAt: Date.now(),
      },
    }
    sessionStorage.setItem(DRAFT_KEY, JSON.stringify(payload))
  } catch {
    /* ignore */
  }
}

export function peekAppInspectorCaseDraft() {
  try {
    return parseJson(sessionStorage.getItem(DRAFT_KEY))
  } catch {
    return null
  }
}

export function consumeAppInspectorCaseDraft(expectedCaseId, expectedProjectId) {
  try {
    const raw = sessionStorage.getItem(DRAFT_KEY)
    if (!raw) return null
    const parsed = parseJson(raw)
    if (!parsed || typeof parsed !== 'object') {
      sessionStorage.removeItem(DRAFT_KEY)
      return null
    }
    const meta = parsed.__meta || {}
    if (expectedCaseId != null && meta.caseId != null && String(meta.caseId) !== String(expectedCaseId)) {
      return null
    }
    if (expectedProjectId != null && meta.projectId != null && String(meta.projectId) !== String(expectedProjectId)) {
      return null
    }
    sessionStorage.removeItem(DRAFT_KEY)
    const { __meta, ...draft } = parsed
    return draft
  } catch {
    return null
  }
}

export function clearAppInspectorCaseDraft() {
  try {
    sessionStorage.removeItem(DRAFT_KEY)
  } catch {
    /* ignore */
  }
}

export function peekAppInspectorResult() {
  try {
    return sessionStorage.getItem(RESULT_KEY)
  } catch {
    return null
  }
}

export function peekInspectorResultParsed() {
  return parseJson(peekAppInspectorResult())
}

export function inspectorResultMatchesCase(result, caseId) {
  if (!result) return false
  if (result.caseId && caseId && String(result.caseId) !== String(caseId)) return false
  return true
}

/** @param {{ type: 'locator', stepPath?: number[], stepIndex?: number, caseId?: string|number, locator: object } | { type: 'steps', steps: array, mode?: 'append'|'replace', caseId?: string|number }} result */
export function setAppInspectorResult(result) {
  try {
    sessionStorage.setItem(RESULT_KEY, JSON.stringify(result))
  } catch {
    /* ignore */
  }
}

export function consumeAppInspectorResult() {
  try {
    const raw = sessionStorage.getItem(RESULT_KEY)
    sessionStorage.removeItem(RESULT_KEY)
    return parseJson(raw)
  } catch {
    return null
  }
}

export function formatInspectorStepPathLabel(stepPath) {
  if (!Array.isArray(stepPath) || !stepPath.length) return ''
  if (stepPath.length === 1) return `步骤 ${stepPath[0] + 1}`
  const parts = [`步骤 ${stepPath[0] + 1}`]
  for (let i = 1; i < stepPath.length; i += 2) {
    parts.push(`分支 ${stepPath[i] + 1}`)
    if (stepPath[i + 1] != null) {
      parts.push(`子步 ${stepPath[i + 1] + 1}`)
    }
  }
  return parts.join(' · ')
}
