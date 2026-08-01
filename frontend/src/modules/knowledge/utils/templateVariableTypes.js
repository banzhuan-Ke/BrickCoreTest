export const VALUE_TYPE_OPTIONS = [
  { value: 'text', label: '单行文本' },
  { value: 'textarea', label: '多行文本' },
  { value: 'date', label: '日期' },
  { value: 'table', label: '表格循环' },
  { value: 'lines', label: '多行列表' }
]

export const BUILTIN_VALUE_TYPE_OPTIONS = [
  { value: 'auto', label: '自动注入' },
  ...VALUE_TYPE_OPTIONS
]

export const VALUE_TYPE_LABEL = Object.fromEntries(
  [...BUILTIN_VALUE_TYPE_OPTIONS, ...VALUE_TYPE_OPTIONS].map(o => [o.value, o.label])
)

export function valueTypeLabel(type) {
  return VALUE_TYPE_LABEL[type] || type || '—'
}

export function valueTypeTag(type) {
  if (type === 'table') return 'warning'
  if (type === 'date') return 'success'
  if (type === 'textarea' || type === 'lines') return 'info'
  if (type === 'auto') return ''
  return 'primary'
}

export function defaultTableSchema() {
  return {
    columns: [
      { key: 'col1', label: '列1', input: 'text' },
      { key: 'col2', label: '列2', input: 'text' }
    ]
  }
}

export function emptyTableRow(schema) {
  const row = {}
  for (const col of schema?.columns || []) {
    row[col.key] = ''
  }
  return row
}

export const USER_WIZARD_BUILTIN = new Set([
  'tester_name',
  'approver',
  'test_environment',
  'plan_start_date',
  'plan_end_date',
  'plan_owner'
])

export function mapVariableToWizardField(v) {
  return {
    name: v.name,
    label: v.label || v.name,
    description: v.description || '',
    value_hint: v.value_hint || v.description || '',
    default_value: v.default_value || '',
    value_type: v.value_type || 'text',
    value_schema: v.value_schema || null
  }
}
