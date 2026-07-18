/**
 * 步骤操作工具函数
 * 提供步骤相关的通用方法
 */

import { ProjectStore } from '@/stores/module/ProjectStore.js'
import { applyDefaultAppIdToStepParams } from '@/utils/appStepMeta.js'

/**
 * 生成唯一步骤ID
 * @returns {string} 步骤ID
 */
export function generateStepId() {
  const timestamp = Date.now()
  const random = Math.random().toString(36).substring(2, 9)
  return `step_${timestamp}_${random}`
}

/** 检查步骤树中是否存在缺少 id 的节点 */
export function stepsMissingIds(steps) {
  if (!Array.isArray(steps)) return false
  for (const step of steps) {
    if (!step?.id) {
      if (step?._keywordDragPlaceholder) continue
      return true
    }
    if (step.method === 'condition_branch' && Array.isArray(step.branches)) {
      for (const branch of step.branches) {
        if (stepsMissingIds(branch.steps)) return true
      }
    }
  }
  return false
}

/**
 * 为缺少 id 的步骤（含条件分支内嵌步骤）补全 id，避免拖拽时与占位项混淆
 * @param {Array} steps
 * @returns {Array}
 */
export function isValidStepPath(path) {
  return Array.isArray(path) && path.length >= 1 && path.length % 2 === 1
}

export function getStepAtPath(steps, path) {
  if (!Array.isArray(steps) || !isValidStepPath(path)) return null
  if (path.length === 1) return steps[path[0]] ?? null
  const walk = (arr, p) => {
    if (!arr || !p.length) return null
    if (p.length === 1) return arr[p[0]] ?? null
    const step = arr[p[0]]
    const branch = step?.branches?.[p[1]]
    if (p.length === 3) return branch?.steps?.[p[2]] ?? null
    return walk(branch?.steps, p.slice(2))
  }
  return walk(steps, path)
}

export function updateStepAtPath(steps, path, updatedStep) {
  const copy = JSON.parse(JSON.stringify(steps || []))
  if (!isValidStepPath(path)) return copy
  const setAt = (arr, p, value) => {
    if (p.length === 1) {
      arr[p[0]] = value
      return true
    }
    const step = arr[p[0]]
    if (!step?.branches?.[p[1]]?.steps) return false
    if (p.length === 3) {
      step.branches[p[1]].steps[p[2]] = value
      return true
    }
    return setAt(step.branches[p[1]].steps, p.slice(2), value)
  }
  setAt(copy, path, updatedStep)
  return copy
}

/** 将路径上的单步替换为多条步骤（如智能步骤编号拆分） */
export function replaceStepAtPathWithMultiple(steps, path, newSteps) {
  const copy = JSON.parse(JSON.stringify(steps || []))
  if (!isValidStepPath(path) || !Array.isArray(newSteps) || newSteps.length === 0) return copy
  const replaceAt = (arr, p, replacements) => {
    if (p.length === 1) {
      arr.splice(p[0], 1, ...replacements)
      return true
    }
    const step = arr[p[0]]
    const branch = step?.branches?.[p[1]]
    if (!branch?.steps) return false
    if (p.length === 3) {
      branch.steps.splice(p[2], 1, ...replacements)
      return true
    }
    return replaceAt(branch.steps, p.slice(2), replacements)
  }
  replaceAt(copy, path, newSteps)
  return copy
}

export function updateStepLocatorAtPath(steps, path, locator) {
  const step = getStepAtPath(steps, path)
  if (!step || !isValidStepPath(path)) {
    return { steps: steps || [], updated: false }
  }
  const updated = {
    ...JSON.parse(JSON.stringify(step)),
    params: {
      ...step.params,
      locator: JSON.parse(JSON.stringify(locator)),
    },
  }
  if (updated.params.locator_ref) delete updated.params.locator_ref
  return {
    steps: updateStepAtPath(steps, path, updated),
    updated: true,
  }
}

export function ensureStepsHaveIds(steps) {
  if (!Array.isArray(steps)) return []
  return steps.map((step) => {
    if (!step || typeof step !== 'object') return step
    if (step._keywordDragPlaceholder) return { ...step }
    const next = step.id ? { ...step } : { ...step, id: generateStepId() }
    if (next.method === 'condition_branch' && Array.isArray(next.branches)) {
      next.branches = next.branches.map((branch) => ({
        ...branch,
        id: branch.id || `branch_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`,
        steps: ensureStepsHaveIds(branch.steps || []),
      }))
    }
    return next
  })
}

/** 判断是否为从左侧关键字面板拖入、尚未规范化的占位对象 */
export function isKeywordDragPlaceholder(step, rawData = {}) {
  if (!step || typeof step !== 'object') return false
  if (step._keywordDragPlaceholder) return true
  if (step.id || step.desc || step.config) return false
  const method = (rawData.method || '').trim()
  if (method && (step.method || '').trim() === method) return true
  const keyword = (rawData.keyword || rawData.name || '').trim()
  if (keyword && (step.keyword || step.name || '').trim() === keyword) return true
  return false
}

/** 左侧关键字面板 data-step 序列化（排除 icon 等不可 JSON 字段） */
export function serializeKeywordForDrag(item) {
  if (!item || typeof item !== 'object') return '{}'
  return JSON.stringify({
    keyword: item.keyword || item.name || '',
    name: item.name || item.keyword || '',
    method: item.method || '',
    params: item.params ? JSON.parse(JSON.stringify(item.params)) : {},
    is_container: item.is_container,
    branches: item.branches ? JSON.parse(JSON.stringify(item.branches)) : undefined,
  })
}

/** 左侧关键字拖入时的占位对象（无 id，由 applyKeywordDragStep 替换） */
export function cloneKeywordForDrag(keyword) {
  const cloned = {
    ...keyword,
    _keywordDragPlaceholder: true,
    params: keyword.params ? JSON.parse(JSON.stringify(keyword.params)) : {},
  }
  delete cloned.id
  if (keyword.is_container !== undefined) {
    cloned.is_container = keyword.is_container
  }
  if (keyword.branches) {
    cloned.branches = JSON.parse(JSON.stringify(keyword.branches))
  }
  return cloned
}

/**
 * 拖入关键字后合并为规范步骤（替换 clone 占位，避免重复插入）
 * @returns {{ steps: Array, insertIndex: number }}
 */
export function applyKeywordDragStep(steps, rawData, newIndex) {
  const newStep = buildStepFromKeyword(rawData)
  const list = [...steps]
  const placeholderIndex = list.findIndex((s) => isKeywordDragPlaceholder(s, rawData))
  if (placeholderIndex >= 0) {
    list[placeholderIndex] = newStep
    return { steps: list, insertIndex: placeholderIndex }
  }
  const safeIndex = Math.max(0, Math.min(newIndex, list.length))
  list.splice(safeIndex, 0, newStep)
  return { steps: list, insertIndex: safeIndex }
}

/** 步骤卡片参数预览：格式化 locator 等对象，避免 [object Object] */
export function formatStepParamValue(value) {
  if (value === null || value === undefined || value === '') return null
  if (typeof value === 'object') {
    if (Array.isArray(value)) {
      return value.length ? `[${value.length}项]` : null
    }
    if (value.by !== undefined) {
      const part = value.value ?? value.text ?? ''
      return part ? `${value.by}=${part}` : String(value.by)
    }
    try {
      const text = JSON.stringify(value)
      return text.length > 40 ? `${text.slice(0, 40)}...` : text
    } catch {
      return '[对象]'
    }
  }
  const str = String(value)
  return str.length > 40 ? `${str.slice(0, 40)}...` : str
}

/**
 * 从关键字面板数据构建规范步骤对象
 */
export function buildStepFromKeyword(rawData) {
  const newStep = {
    id: generateStepId(),
    keyword: rawData.keyword || rawData.name || '未知操作',
    desc: rawData.name || rawData.keyword || '未知操作',
    method: rawData.method || '',
    params: rawData.params ? JSON.parse(JSON.stringify(rawData.params)) : {},
    children: [],
    config: { timeout: 30000, retry: false, pre_wait_ms: 0 },
  }
  if (rawData.method === 'condition_branch' || rawData.is_container) {
    newStep.is_container = true
    newStep.branches = rawData.branches
      ? JSON.parse(JSON.stringify(rawData.branches))
      : [
          {
            id: `branch_${Date.now()}`,
            name: '分支1',
            condition: { type: 'element_visible', locator: '', operator: 'is_true' },
            steps: [],
          },
          {
            id: `else_branch_${Date.now()}`,
            name: '默认分支',
            condition: { type: 'else' },
            steps: [],
          },
        ]
  }
  const proStore = ProjectStore()
  newStep.params = applyDefaultAppIdToStepParams(
    newStep.method,
    newStep.params,
    proStore.projectInfo,
    []
  )
  return newStep
}

/**
 * 将后端展开的片段步骤转为用例内可编辑的普通步骤（新 id、去掉片段溯源字段）
 * @param {Array} steps
 * @returns {Array}
 */
export function normalizeExpandedFragmentSteps(steps) {
  if (!Array.isArray(steps)) return []
  return steps.map((step) => {
    const next = { ...step, id: generateStepId() }
    delete next._from_fragment
    if (next.method === 'condition_branch' && Array.isArray(next.branches)) {
      next.branches = next.branches.map((branch) => ({
        ...branch,
        steps: normalizeExpandedFragmentSteps(branch.steps),
      }))
    }
    return next
  })
}

/**
 * 克隆步骤对象
 * @param {Object} step 步骤对象
 * @returns {Object} 克隆后的步骤
 */
export function cloneStep(step) {
  return JSON.parse(JSON.stringify(step))
}

/**
 * 复制步骤并生成新的 id（含条件分支内嵌步骤）
 * @param {Object} step 步骤对象
 * @returns {Object} 复制后的步骤
 */
export function duplicateStepWithNewIds(step) {
  const cloned = cloneStep(step)
  return assignNewStepIds(cloned)
}

/**
 * 去掉展开片段时附带的溯源字段，便于写入新片段
 * @param {Object} step
 * @returns {Object}
 */
export function stripStepProvenance(step) {
  const next = cloneStep(step)
  delete next._from_fragment
  if (next.method === 'condition_branch' && Array.isArray(next.branches)) {
    next.branches = next.branches.map((branch) => ({
      ...branch,
      steps: (branch.steps || []).map(stripStepProvenance),
    }))
  }
  return next
}

/**
 * 按索引提取步骤并生成新 id（用于从用例生成片段）
 * @param {Array} steps
 * @param {number[]} indices
 * @returns {Array}
 */
export function extractStepsWithNewIds(steps, indices) {
  const sorted = [...indices].sort((a, b) => a - b)
  return sorted
    .filter((index) => index >= 0 && index < steps.length)
    .map((index) => assignNewStepIds(stripStepProvenance(steps[index])))
}

/**
 * 构建片段引用步骤
 * @param {{ id: number, name: string, version?: number, description?: string }} fragment
 * @returns {Object}
 */
export function buildFragmentRefStep(fragment) {
  return {
    id: generateStepId(),
    method: 'fragment_ref',
    keyword: `片段：${fragment.name}`,
    desc: fragment.description || fragment.name,
    params: {
      fragment_id: fragment.id,
      fragment_version: fragment.version,
      fragment_name: fragment.name,
      variables: {},
    },
    is_fragment_ref: true,
  }
}

function assignNewStepIds(step) {
  const next = { ...step, id: generateStepId() }
  if (next.method === 'condition_branch' && Array.isArray(next.branches)) {
    next.branches = next.branches.map((branch) => ({
      ...branch,
      id: `branch_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`,
      steps: (branch.steps || []).map(assignNewStepIds),
    }))
  }
  return next
}

/**
 * 查找步骤在数组中的索引
 * @param {Array} steps 步骤数组
 * @param {string} stepId 步骤ID
 * @returns {number} 索引，找不到返回 -1
 */
export function findStepIndex(steps, stepId) {
  return steps.findIndex(s => s.id === stepId)
}

/**
 * 递归查找步骤（支持嵌套）
 * @param {Array} steps 步骤数组
 * @param {string} stepId 步骤ID
 * @returns {Object|null} 找到的步骤
 */
export function findStepRecursive(steps, stepId) {
  for (const step of steps) {
    if (step.id === stepId) {
      return step
    }
    if (step.children?.length) {
      const found = findStepRecursive(step.children, stepId)
      if (found) return found
    }
  }
  return null
}

/**
 * 移动步骤到新位置
 * @param {Array} steps 步骤数组
 * @param {number} fromIndex 原索引
 * @param {number} toIndex 目标索引
 * @returns {Array} 新的步骤数组
 */
export function moveStep(steps, fromIndex, toIndex) {
  const newSteps = [...steps]
  const [moved] = newSteps.splice(fromIndex, 1)
  newSteps.splice(toIndex, 0, moved)
  return newSteps
}

/**
 * 验证步骤是否可嵌套
 * @param {Object} parentStep 父步骤
 * @param {Object} childStep 子步骤
 * @returns {boolean} 是否可嵌套
 */
export function canNest(parentStep, childStep) {
  // 只有容器步骤才能包含子步骤
  const containerMethods = ['if', 'for', 'while', 'try_catch']
  if (!containerMethods.includes(parentStep?.method)) {
    return false
  }
  
  // 子步骤不能是另一个容器（避免嵌套过深）
  if (containerMethods.includes(childStep?.method)) {
    return false
  }
  
  return true
}

/**
 * 获取步骤类型的中文名称
 * @param {string} method 步骤方法名
 * @returns {string} 中文名称
 */
export function getStepTypeName(method) {
  const typeMap = {
    open_browser: '浏览器',
    close: '浏览器',
    open_url: '导航',
    go_back: '导航',
    refresh: '导航',
    fill_value: '元素操作',
    click_ele: '元素操作',
    clear_value: '元素操作',
    kw_assert_visible: '断言',
    kw_assert_text_contains: '断言',
    kw_assert_element_text: '断言',
    kw_assert_element_text_contains: '断言',
    condition_branch: '条件',
  }
  return typeMap[method] || '其他'
}

/**
 * 格式化步骤显示
 * @param {Object} step 步骤对象
 * @returns {string} 格式化后的字符串
 */
export function formatStepDisplay(step) {
  if (!step) return ''
  
  let display = step.keyword || step.desc
  
  // 添加关键参数信息
  if (step.params?.url) {
    display += ` (${truncate(step.params.url, 30)})`
  } else if (step.params?.locator) {
    display += ` (${truncate(step.params.locator, 20)})`
  } else if (step.params?.selector) {
    display += ` (${truncate(step.params.selector, 20)})`
  }
  
  return display
}

/**
 * 截断字符串
 * @param {string} str 字符串
 * @param {number} maxLength 最大长度
 * @returns {string} 截断后的字符串
 */
function truncate(str, maxLength) {
  if (!str || str.length <= maxLength) return str
  return str.substring(0, maxLength) + '...'
}

/**
 * 验证步骤参数是否完整
 * @param {Object} step 步骤对象
 * @returns {Array} 错误信息数组
 */
export function validateStep(step) {
  const errors = []
  
  if (!step.keyword) {
    errors.push('步骤名称不能为空')
  }
  
  // 根据方法类型验证必填参数
  const requiredParams = {
    open_url: ['url'],
    click_ele: ['locator'],
    fill_value: ['locator'],
    kw_assert_visible: ['locator'],
    kw_assert_text_contains: ['text'],
    kw_assert_element_text: ['locator', 'text'],
    kw_assert_element_text_contains: ['locator', 'text'],
  }
  
  const required = requiredParams[step.method] || []
  for (const param of required) {
    if (!step.params?.[param]) {
      errors.push(`参数 "${param}" 不能为空`)
    }
  }
  
  return errors
}
