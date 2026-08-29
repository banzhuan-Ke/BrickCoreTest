import { mergeBrowserLabExecForm } from './browserLabExecOptions.js'
import { browserLabDeviceLabel } from './browserLabDeviceLabel.js'

export function resolveAiConfigLabel(aiConfigId, configs = []) {
  if (!aiConfigId) return '默认模型（按场景配置）'
  const c = configs.find((x) => x.id === aiConfigId)
  return c ? `${c.name} (${c.model})` : `配置 #${aiConfigId}`
}

export function buildExecConfirmContext({
  title = '确认执行',
  name = '',
  startUrl = '',
  taskText = '',
  source,
  aiConfigId = null,
  aiConfigs = [],
  caseId = null,
  taskId = null,
}) {
  const execForm = mergeBrowserLabExecForm(source || {})
  const cid = aiConfigId ?? source?.ai_config_id ?? source?.config_json?.ai_config_id ?? null
  return {
    title,
    name,
    startUrl: startUrl || source?.start_url || '',
    taskText: taskText || source?.task_text || '',
    execForm,
    aiConfigLabel: resolveAiConfigLabel(cid, aiConfigs),
    caseId: caseId ?? source?.id ?? source?.case_id ?? null,
    taskId,
  }
}

export function formatExecOptionTags(form) {
  const tags = []
  tags.push(form.headless === false ? '有头模式' : '无头模式')
  tags.push(`最大 ${form.max_steps ?? 25} 步`)
  if (form.use_vision !== false) tags.push('Vision')
  if (form.generate_gif !== false) tags.push('回放 GIF')
  if (form.use_action_cache !== false) tags.push('动作缓存')
  if (form.force_refresh_cache) tags.push('强制刷新缓存')
  if (form.enable_browser_restart !== false) tags.push('CDP 续跑')
  return tags
}

export function findOnlineDevice(devices, deviceId) {
  if (!deviceId) return null
  return devices.find((d) => String(d.id) === String(deviceId)) || null
}

export { browserLabDeviceLabel }
