/** Runner 设备下拉/摘要展示文案 */
export function browserLabDeviceLabel(device) {
  if (!device) return '—'
  const name = device.name || device.username || device.id
  const engines = (device.runner_engine_types || ['web']).join('/')
  return `${name} (${device.ip || '—'}) · ${engines}`
}
