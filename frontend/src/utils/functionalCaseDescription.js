/**
 * 将功能用例拼装为 Web 用例描述（与后端 build_case_description_from_functional 对齐）
 */
export function buildFunctionalCaseDescription(fc, options = {}) {
  if (!fc) return ''
  const { pageUrl = '', extraContext = '', includeRecordHint = false } = options
  const parts = []

  if (fc.title) parts.push(`【用例】${fc.title}`)
  if (fc.precondition) parts.push(`【前置条件】${fc.precondition}`)

  const steps = fc.steps || []
  if (steps.length) {
    parts.push('【测试步骤与预期】')
    steps.forEach((st, i) => {
      const step = (st.step || '').trim()
      const expect = (st.expect || '').trim()
      if (!step && !expect) return
      let line = `${i + 1}. ${step || '（无步骤描述）'}`
      if (expect) line += ` → 预期：${expect}`
      parts.push(line)
    })
  }

  if (pageUrl?.trim()) parts.push(`【目标页面】${pageUrl.trim()}`)
  if (extraContext?.trim()) parts.push(`【细节补充】\n${extraContext.trim()}`)

  if (includeRecordHint) {
    parts.push('【录制说明】登录与前置导航由人工在浏览器中完成；可在录制结束后的「测试描述 / AI 优化」中补充业务背景。')
  }

  return parts.join('\n\n').slice(0, 4000)
}
