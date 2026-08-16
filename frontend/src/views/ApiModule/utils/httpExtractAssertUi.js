/**
 * 接口用例 / Token 授权：变量提取与断言的统一文案与选项。
 * 存储值保持后端契约（json/header/regex、status_code/json_path/...）不变。
 */

export const EXTRACTOR_SOURCE_GROUPS = [
  {
    label: '响应体',
    options: [
      {
        value: 'json',
        label: 'JSON 路径',
        placeholder: '$.data.token',
        hint: '从响应 Body 按 JSONPath 提取',
      },
      {
        value: 'regex',
        label: '正则匹配',
        placeholder: '"token"\\s*:\\s*"([^"]+)"',
        hint: '从响应 Body 文本正则提取；有捕获组时取第 1 组',
      },
    ],
  },
  {
    label: '响应头',
    options: [
      {
        value: 'header',
        label: 'Header 名',
        placeholder: 'Set-Cookie',
        hint: '从响应头提取；填写 Header 名称（如 Set-Cookie、Authorization）',
      },
    ],
  },
]

export const ASSERTION_TYPE_GROUPS = [
  {
    label: '状态',
    options: [
      {
        value: 'status_code',
        label: 'HTTP 状态码',
        needsTarget: false,
        targetPlaceholder: '',
      },
    ],
  },
  {
    label: '响应体',
    options: [
      {
        value: 'json_path',
        label: 'JSON 路径',
        needsTarget: true,
        targetPlaceholder: '$.data.id',
      },
      {
        value: 'contains',
        label: '全文包含',
        needsTarget: false,
        targetPlaceholder: '',
      },
      {
        value: 'not_contains',
        label: '全文不包含',
        needsTarget: false,
        targetPlaceholder: '',
      },
    ],
  },
  {
    label: '响应头',
    options: [
      {
        value: 'header',
        label: '指定 Header',
        needsTarget: true,
        targetPlaceholder: 'Content-Type',
      },
    ],
  },
]

export const WS_ASSERTION_TYPE_GROUPS = [
  {
    label: 'WebSocket',
    options: [
      {
        value: 'ws_contains',
        label: '消息全文包含',
        needsTarget: false,
        targetPlaceholder: '',
      },
      {
        value: 'ws_json_path',
        label: '消息 JSON 路径',
        needsTarget: true,
        targetPlaceholder: '$.type',
      },
      {
        value: 'ws_message_count',
        label: '消息条数',
        needsTarget: false,
        targetPlaceholder: '',
      },
    ],
  },
]

function _flatOptions(groups) {
  return groups.flatMap((g) => g.options || [])
}

export function findExtractorSourceOption(source) {
  return _flatOptions(EXTRACTOR_SOURCE_GROUPS).find((o) => o.value === source) || null
}

export function extractorPathPlaceholder(source) {
  return findExtractorSourceOption(source)?.placeholder || '提取表达式'
}

export function extractorSourceLabel(source) {
  const opt = findExtractorSourceOption(source)
  if (!opt) return source || '-'
  const group = EXTRACTOR_SOURCE_GROUPS.find((g) => g.options.some((o) => o.value === source))
  return group ? `${group.label} · ${opt.label}` : opt.label
}

export function findAssertionTypeOption(type, { includeWs = false } = {}) {
  const groups = includeWs
    ? [...ASSERTION_TYPE_GROUPS, ...WS_ASSERTION_TYPE_GROUPS]
    : ASSERTION_TYPE_GROUPS
  return _flatOptions(groups).find((o) => o.value === type) || null
}

export function assertionNeedsTarget(type, { includeWs = false } = {}) {
  const opt = findAssertionTypeOption(type, { includeWs })
  if (opt) return !!opt.needsTarget
  // 未知类型：除状态码/全文包含外默认需要目标
  return !['status_code', 'contains', 'not_contains', 'ws_contains', 'ws_message_count'].includes(type)
}

export function assertionTargetPlaceholder(type, { includeWs = false } = {}) {
  return findAssertionTypeOption(type, { includeWs })?.targetPlaceholder || '目标'
}

export function assertionTargetColumnLabel(type) {
  if (type === 'header') return 'Header 名'
  if (type === 'json_path' || type === 'ws_json_path') return 'JSONPath'
  return '目标'
}

export function assertionTypeLabel(type) {
  const map = {
    status_code: '状态 · HTTP 状态码',
    json_path: '响应体 · JSON 路径',
    header: '响应头 · 指定 Header',
    contains: '响应体 · 全文包含',
    not_contains: '响应体 · 全文不包含',
    ws_contains: 'WebSocket · 消息全文包含',
    ws_json_path: 'WebSocket · 消息 JSON 路径',
    ws_message_count: 'WebSocket · 消息条数',
  }
  return map[type] || type || '-'
}

export function assertionTypeGroups({ includeWs = false } = {}) {
  return includeWs
    ? [...ASSERTION_TYPE_GROUPS, ...WS_ASSERTION_TYPE_GROUPS]
    : ASSERTION_TYPE_GROUPS
}
