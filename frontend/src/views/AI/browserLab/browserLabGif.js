/** 智能浏览器 GIF 预览页链接（Hash 路由须带 /#/ 前缀，否则新标签会落到登录页） */
export function browserLabGifPreviewHref(taskId, projectId) {
  if (!taskId) return ''
  const origin = window.location.origin.replace(/\/$/, '')
  const q = projectId != null ? `?project_id=${projectId}` : ''
  return `${origin}/#/browser-lab/gif/${taskId}${q}`
}
