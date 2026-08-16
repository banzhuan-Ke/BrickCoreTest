/**
 * 插入变量 / 插入工具「引用变量」共用数据源。
 * 约定：项目变量 + 环境变量 + Token 授权 + 内置 + 调用方 extra，禁止只列内置。
 */
import { BUILTIN_VAR_HINTS, isSecretKey, varsObjectToList } from '@/utils/globalVars.js'

export function previewInsertableValue(value, key = '') {
  if (value === null || value === undefined || value === '') return ''
  if (key && isSecretKey(key)) return '••••••'
  let s
  if (typeof value === 'object') {
    try {
      s = JSON.stringify(value)
    } catch {
      return '[Object]'
    }
  } else {
    s = String(value)
  }
  return s.length > 28 ? `${s.slice(0, 28)}…` : s
}

function optionLabel(key, preview = '', description = '') {
  const bits = [key]
  if (description) bits.push(description)
  if (preview) bits.push(preview)
  return bits.join(' · ')
}

/**
 * @param {object} opts
 * @param {object} [opts.projectGlobalVars]
 * @param {object|null} [opts.envGlobalVars] 有环境时传入；null/undefined 表示未选环境
 * @param {Array<{name:string,preview?:any,description?:string}>} [opts.authItems]
 * @param {string[]} [opts.extraVars]
 * @param {boolean} [opts.includeBuiltin=true]
 * @returns {{label:string, items:{key:string,label:string,preview:string,description:string}[]}[]}
 */
export function collectInsertableVarGroups(opts = {}) {
  const {
    projectGlobalVars = {},
    envGlobalVars = undefined,
    authItems = [],
    extraVars = [],
    includeBuiltin = true,
  } = opts

  const groups = []
  const seen = new Set()

  const pushGroup = (label, rawItems) => {
    const cleaned = []
    for (const item of rawItems || []) {
      const key = String(item.key || '').trim()
      if (!key || seen.has(key)) continue
      seen.add(key)
      const preview = item.preview ?? ''
      const description = item.description || ''
      cleaned.push({
        key,
        preview,
        description,
        label: optionLabel(key, preview, description),
      })
    }
    if (cleaned.length) groups.push({ label, items: cleaned })
  }

  pushGroup(
    '项目变量',
    varsObjectToList(projectGlobalVars || {})
      .filter((item) => !item._rawObject)
      .map((item) => ({
        key: item.key,
        preview: previewInsertableValue(item.value, item.key),
        description: item.description || '',
      }))
  )

  if (envGlobalVars !== undefined && envGlobalVars !== null) {
    pushGroup(
      '环境变量',
      varsObjectToList(envGlobalVars || {})
        .filter((item) => !item._rawObject)
        .map((item) => ({
          key: item.key,
          preview: previewInsertableValue(item.value, item.key),
          description: item.description || '',
        }))
    )
  }

  if (Array.isArray(authItems) && authItems.length) {
    pushGroup(
      'Token 授权',
      authItems.map((item) => ({
        key: item.name,
        preview: previewInsertableValue(item.preview, item.name),
        description: item.description || '',
      }))
    )
  }

  if (includeBuiltin) {
    pushGroup(
      '内置变量',
      BUILTIN_VAR_HINTS.map((item) => ({
        key: item.key,
        preview: item.label || '',
        description: '',
      }))
    )
  }

  pushGroup(
    '本用例/额外变量',
    (extraVars || []).filter(Boolean).map((key) => ({
      key: String(key),
      preview: '',
      description: '',
    }))
  )

  return groups
}

/** 扁平 key 列表（去重，组顺序与 collectInsertableVarGroups 一致） */
export function flattenInsertableVarKeys(groups) {
  const keys = []
  for (const g of groups || []) {
    for (const item of g.items || []) {
      if (item.key) keys.push(item.key)
    }
  }
  return keys
}
