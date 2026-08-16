/** 输入步骤 value 动态值模式（W-13） */



export const FILL_VALUE_MODES = [

  { value: 'fixed', label: '固定值' },

  { value: 'random_str', label: '随机字符串' },

  { value: 'random_int', label: '随机数字' },

  { value: 'timestamp', label: '时间戳' },

  { value: 'prefix_timestamp', label: '前缀 + 时间戳' },

  { value: 'datetime', label: '日期时间' },

  { value: 'prefix_datetime', label: '前缀 + 日期时间' },

]



const DYN_RANDOM_INT = '${{random_int}}'

const DYN_RANDOM_STR = '${{random_str}}'

const DYN_TIMESTAMP = '${{timestamp}}'

const DYN_NOW_TIME = '${{now_time}}'



const DYNAMIC_EXACT = {

  [DYN_RANDOM_INT]: 'random_int',

  [DYN_RANDOM_STR]: 'random_str',

  [DYN_TIMESTAMP]: 'timestamp',

  [DYN_NOW_TIME]: 'datetime',

}



function matchPrefixMode(raw, token, mode) {

  if (!raw.endsWith(token) || raw.length <= token.length) return null

  if (raw !== raw.trim()) return null

  return { mode, prefix: raw.slice(0, -token.length), fixed: '' }

}



export function detectFillValueMode(value) {

  const raw = String(value ?? '')

  const exactMode = DYNAMIC_EXACT[raw]

  if (exactMode) {

    return { mode: exactMode, fixed: '', prefix: '' }

  }

  const prefixTs = matchPrefixMode(raw, DYN_TIMESTAMP, 'prefix_timestamp')

  if (prefixTs) return prefixTs

  const prefixDt = matchPrefixMode(raw, DYN_NOW_TIME, 'prefix_datetime')

  if (prefixDt) return prefixDt

  return { mode: 'fixed', fixed: raw, prefix: '' }

}



export function buildFillValue(mode, { fixed = '', prefix = '' } = {}) {

  switch (mode) {

    case 'random_int':

      return DYN_RANDOM_INT

    case 'random_str':

      return DYN_RANDOM_STR

    case 'timestamp':

      return DYN_TIMESTAMP

    case 'datetime':

      return DYN_NOW_TIME

    case 'prefix_timestamp':

      return `${prefix || ''}${DYN_TIMESTAMP}`

    case 'prefix_datetime':

      return `${prefix || ''}${DYN_NOW_TIME}`

    default:

      return fixed

  }

}



export function isFillValueFixedMode(value) {

  return detectFillValueMode(value).mode === 'fixed'

}



export const FILL_VALUE_INPUT_METHODS = new Set([
  'fill_value',
  'frame_fill_value',
  'fill_if_exists',
  'fill_if_visible',
])

