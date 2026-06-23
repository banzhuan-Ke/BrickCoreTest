/**
 * 步骤操作工具函数
 * 提供步骤相关的通用方法
 */

/**
 * 生成唯一步骤ID
 * @returns {string} 步骤ID
 */
export function generateStepId() {
  const timestamp = Date.now()
  const random = Math.random().toString(36).substring(2, 9)
  return `step_${timestamp}_${random}`
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
