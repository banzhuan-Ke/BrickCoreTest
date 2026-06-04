/** 全局 Header 工具函数 */

export function normalizeHeaderList(raw, { keepEmpty = false } = {}) {
  if (!raw) return []
  if (Array.isArray(raw)) {
    return raw
      .filter((h) => h && (keepEmpty || h.key))
      .map((h) => ({
        key: String(h.key || '').trim(),
        value: h.value ?? '',
        description: h.description ?? '',
        enabled: h.enabled !== false,
        source: h.source,
      }))
  }
  if (typeof raw === 'object') {
    return Object.entries(raw).map(([key, value]) => ({
      key,
      value: value ?? '',
      description: '',
      enabled: true,
    }))
  }
  return []
}

/** 合并项目+环境 Header（展示用，含配置层禁用的项） */
export function listRawGlobalHeaders(projectHeaders, envHeaders) {
  const merged = new Map()
  normalizeHeaderList(projectHeaders).forEach((item) => {
    merged.set(item.key, {
      ...item,
      source: 'project',
      configEnabled: item.enabled !== false,
    })
  })
  normalizeHeaderList(envHeaders).forEach((item) => {
    merged.set(item.key, {
      ...item,
      source: 'environment',
      configEnabled: item.enabled !== false,
    })
  })
  return Array.from(merged.values())
}

export function normalizeGlobalHeaderPolicy(policy) {
  const disabled = policy?.disabled_keys
  const hasEnabledKeys = policy && Object.prototype.hasOwnProperty.call(policy, 'enabled_keys')
  return {
    disabled_keys: Array.isArray(disabled) ? disabled.filter(Boolean) : [],
    enabled_keys: hasEnabledKeys
      ? (Array.isArray(policy.enabled_keys) ? policy.enabled_keys.filter(Boolean) : [])
      : undefined,
  }
}

export function usesOptInPolicy(policy) {
  return normalizeGlobalHeaderPolicy(policy).enabled_keys !== undefined
}

function availableConfigKeys(rows) {
  return new Set(rows.filter((r) => r.configEnabled !== false).map((r) => r.key))
}

/** 计算接口层启用的全局 Header key 集合 */
export function resolveApiEnabledKeys(apiPolicy, rows) {
  const available = availableConfigKeys(rows)
  const norm = normalizeGlobalHeaderPolicy(apiPolicy)
  if (usesOptInPolicy(norm)) {
    return new Set((norm.enabled_keys || []).filter((k) => available.has(k)))
  }
  const disabled = new Set(norm.disabled_keys || [])
  return new Set([...available].filter((k) => !disabled.has(k)))
}

/** 计算用例层最终启用的全局 Header key 集合（接口策略 + 用例 disabled_keys） */
export function resolveEffectiveEnabledKeys(apiPolicy, casePolicy, rows) {
  const enabled = resolveApiEnabledKeys(apiPolicy, rows)
  const caseDisabled = new Set(normalizeGlobalHeaderPolicy(casePolicy).disabled_keys || [])
  caseDisabled.forEach((k) => enabled.delete(k))
  return enabled
}

export function buildGlobalHeadersForUi(projectHeaders, envHeaders, policy, apiPolicy = null) {
  const rows = listRawGlobalHeaders(projectHeaders, envHeaders)
  const isCaseLevel = apiPolicy != null

  if (isCaseLevel) {
    const effective = resolveEffectiveEnabledKeys(apiPolicy, policy, rows)
    const apiEnabled = resolveApiEnabledKeys(apiPolicy, rows)
    return rows.map((item) => ({
      ...item,
      enabled: effective.has(item.key),
      configDisabled: item.configEnabled === false,
      apiDisabled: item.configEnabled !== false && !apiEnabled.has(item.key),
    }))
  }

  const norm = normalizeGlobalHeaderPolicy(policy)
  const optIn = usesOptInPolicy(norm)
  return rows.map((item) => {
    if (item.configEnabled === false) {
      return { ...item, enabled: false, configDisabled: true, apiDisabled: false }
    }
    const enabled = optIn
      ? (norm.enabled_keys || []).includes(item.key)
      : !(norm.disabled_keys || []).includes(item.key)
    return { ...item, enabled, configDisabled: false, apiDisabled: false }
  })
}

export function toggleGlobalHeaderKey(policy, key, enabled) {
  const normalized = normalizeGlobalHeaderPolicy(policy)
  const set = new Set(normalized.disabled_keys)
  if (enabled) {
    set.delete(key)
  } else {
    set.add(key)
  }
  return { ...policy, disabled_keys: Array.from(set) }
}

export function toggleEnabledHeaderKey(policy, key, enabled) {
  const normalized = normalizeGlobalHeaderPolicy(policy)
  const base = { ...policy, disabled_keys: normalized.disabled_keys }
  const set = new Set(normalized.enabled_keys || [])
  if (enabled) {
    set.add(key)
  } else {
    set.delete(key)
  }
  return { ...base, enabled_keys: Array.from(set) }
}

export function toggleGlobalHeaderForLevel(policy, key, enabled, { apiPolicy = null, rows = [] } = {}) {
  if (apiPolicy != null) {
    const apiEnabled = resolveApiEnabledKeys(apiPolicy, rows)
    if (enabled && !apiEnabled.has(key)) {
      return policy
    }
    return toggleGlobalHeaderKey(policy, key, enabled)
  }
  if (usesOptInPolicy(policy)) {
    return toggleEnabledHeaderKey(policy, key, enabled)
  }
  return toggleGlobalHeaderKey(policy, key, enabled)
}

export function importGlobalHeadersToLocal(localHeaders, globalItems, keys = null, { includeAll = false } = {}) {
  const local = normalizeHeaderList(localHeaders, { keepEmpty: true })
  const localKeys = new Set(local.map((h) => h.key).filter(Boolean))
  let targets = keys ? globalItems.filter((g) => keys.includes(g.key)) : globalItems
  if (!includeAll) {
    targets = targets.filter(
      (g) => g.enabled !== false && g.configEnabled !== false && g.apiDisabled !== true
    )
  }
  const imported = []
  targets.forEach((g) => {
    if (!localKeys.has(g.key)) {
      const suffix = g.configDisabled ? '（配置已禁用，导入后仅本地生效）' : ''
      local.push({
        key: g.key,
        value: g.value,
        description: g.description ? `来自全局: ${g.description}${suffix}` : `来自全局 Header${suffix}`,
      })
      localKeys.add(g.key)
      imported.push(g.key)
    }
  })
  return { headers: local, imported }
}

export function validateDefaultHeaders(list) {
  const items = normalizeHeaderList(list)
  const seen = new Set()
  for (const item of items) {
    if (!item.key) return { ok: false, error: 'Header 名称不能为空' }
    if (seen.has(item.key)) return { ok: false, error: `Header key 重复: ${item.key}` }
    seen.add(item.key)
  }
  return { ok: true, items }
}

export const GLOBAL_HEADER_SOURCE_LABEL = {
  project: '项目',
  environment: '环境',
}
