/**
 * 根据 JSON 响应示例智能推荐断言规则
 */

const MAX_ASSERTIONS = 25
const MAX_DEPTH = 4

function isStatusLikePath(path) {
  const lower = path.toLowerCase()
  return (
    lower.endsWith('.status') ||
    lower.endsWith('.code') ||
    lower === '$.status' ||
    lower === '$.code' ||
    lower.endsWith('statuscode')
  )
}

function truncateText(text, max = 40) {
  if (text.length <= max) return text
  return `${text.slice(0, max)}…`
}

/**
 * @param {string} path JSONPath
 * @param {*} value 字段值
 * @returns {object|null}
 */
export function suggestAssertionForValue(path, value) {
  if (value === null || value === undefined) {
    return {
      type: 'json_path',
      target: path,
      operator: 'not_equals',
      expected: null,
      description: `字段 ${path} 非空`,
    }
  }

  const valueType = typeof value

  if (valueType === 'boolean') {
    return {
      type: 'json_path',
      target: path,
      operator: 'equals',
      expected: value,
      description: `字段 ${path} 为 ${value}`,
    }
  }

  if (valueType === 'number') {
    if (isStatusLikePath(path)) {
      return {
        type: 'json_path',
        target: path,
        operator: 'equals',
        expected: value,
        description: `字段 ${path} 等于 ${value}`,
      }
    }
    return {
      type: 'json_path',
      target: path,
      operator: 'equals',
      expected: value,
      description: `字段 ${path} 等于 ${value}`,
    }
  }

  if (valueType === 'string') {
    if (value === '') {
      return {
        type: 'json_path',
        target: path,
        operator: 'not_equals',
        expected: '',
        description: `字段 ${path} 非空字符串`,
      }
    }
    if (isStatusLikePath(path) && /^\d+$/.test(value)) {
      return {
        type: 'json_path',
        target: path,
        operator: 'equals',
        expected: value,
        description: `字段 ${path} 等于 ${value}`,
      }
    }
    if (value.length > 80) {
      return {
        type: 'json_path',
        target: path,
        operator: 'contains',
        expected: value.slice(0, 32),
        description: `字段 ${path} 包含关键片段`,
      }
    }
    return {
      type: 'json_path',
      target: path,
      operator: 'equals',
      expected: value,
      description: `字段 ${path} 等于 "${truncateText(value)}"`,
    }
  }

  if (Array.isArray(value)) {
    if (value.length === 0) {
      return {
        type: 'json_path',
        target: path,
        operator: 'equals',
        expected: [],
        description: `字段 ${path} 为空数组`,
      }
    }
    return {
      type: 'json_path',
      target: path,
      operator: 'not_equals',
      expected: null,
      description: `字段 ${path} 为非空数组（长度 ${value.length}）`,
    }
  }

  return null
}

function walkJson(value, prefix, depth, results) {
  if (results.length >= MAX_ASSERTIONS || depth > MAX_DEPTH) return

  if (value === null || value === undefined || typeof value !== 'object') {
    const assertion = suggestAssertionForValue(prefix, value)
    if (assertion) results.push(assertion)
    return
  }

  if (Array.isArray(value)) {
    const assertion = suggestAssertionForValue(prefix, value)
    if (assertion) results.push(assertion)
    if (value.length > 0 && typeof value[0] === 'object' && value[0] !== null) {
      walkJson(value[0], `${prefix}[0]`, depth + 1, results)
    }
    return
  }

  for (const key of Object.keys(value)) {
    if (results.length >= MAX_ASSERTIONS) break
    const childPath = prefix ? `${prefix}.${key}` : `$.${key}`
    const child = value[key]
    if (child !== null && typeof child === 'object') {
      walkJson(child, childPath, depth + 1, results)
    } else {
      const assertion = suggestAssertionForValue(childPath, child)
      if (assertion) results.push(assertion)
    }
  }
}

/**
 * 从 JSON 文本生成断言列表（含状态码）
 * @param {string} jsonInput
 * @returns {{ assertions: object[], error?: string }}
 */
export function buildAssertionsFromJson(jsonInput) {
  const result = [
    {
      type: 'status_code',
      target: '',
      operator: 'equals',
      expected: '200',
      description: 'HTTP 状态码为 200',
    },
  ]

  const text = (jsonInput || '').trim()
  if (!text) {
    return { assertions: result }
  }

  try {
    const data = JSON.parse(text)
    if (typeof data === 'object' && data !== null && !Array.isArray(data)) {
      walkJson(data, '', 0, result)
    } else if (Array.isArray(data) && data.length > 0 && typeof data[0] === 'object') {
      walkJson(data[0], '$[0]', 0, result)
    } else {
      const assertion = suggestAssertionForValue('$', data)
      if (assertion) result.push(assertion)
    }
  } catch {
    return { assertions: [], error: 'JSON 格式错误，请检查输入' }
  }

  return { assertions: result.slice(0, MAX_ASSERTIONS + 1) }
}
