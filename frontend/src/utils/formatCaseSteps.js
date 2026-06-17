/** 将 steps JSON 格式化为列表展示用多行文本 */
export function formatNumberedSteps(steps, field = 'step') {
  const list = Array.isArray(steps) ? steps : []
  return list
    .map((st, i) => {
      const text =
        st && typeof st === 'object'
          ? (st[field] ?? st.step ?? st.expect ?? '')
          : String(st ?? '')
      const trimmed = String(text).trim()
      return trimmed ? `${i + 1}. ${trimmed}` : ''
    })
    .filter(Boolean)
    .join('\n')
}

export function formatStepsText(steps) {
  return formatNumberedSteps(steps, 'step')
}

export function formatExpectsText(steps) {
  return formatNumberedSteps(steps, 'expect')
}
