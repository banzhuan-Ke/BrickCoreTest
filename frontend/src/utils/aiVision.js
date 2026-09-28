/**
 * AI 配置是否支持多模态（Vision）。
 * 优先读 supports_vision；旧数据无字段时回退模型名启发式。
 */
export function isLikelyVisionModelName(model) {
  const m = (model || '').toLowerCase()
  return (
    m.includes('vl') ||
    m.includes('vision') ||
    m.includes('gpt-4o') ||
    m.includes('gpt-4-turbo') ||
    m.includes('claude-3') ||
    m.includes('gemini') ||
    m.includes('qvq')
  )
}

export function configSupportsVision(config) {
  if (!config) return false
  if (typeof config.supports_vision === 'boolean') {
    return config.supports_vision
  }
  return isLikelyVisionModelName(config.model)
}

export function visionUnsupportedTip(config, action = '多模态/读图') {
  const name = (config?.name || '当前配置').trim()
  const model = (config?.model || '').trim()
  const label = model ? `「${name}」（${model}）` : `「${name}」`
  return `${label}未开启「支持多模态」，无法用于${action}。请到「平台配置 → AI 模型」开启该开关，或改选 Vision 模型。`
}
