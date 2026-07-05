/** Runner 设备引擎能力（与 AppRunDialog / AppInspector 一致） */
export function deviceEngineTypes(device) {
  const types = device?.runner_engine_types
  return Array.isArray(types) && types.length ? types : ['web']
}

export function deviceSupportsEngine(device, engine) {
  return deviceEngineTypes(device).includes(engine)
}

export function filterOnlineDevicesByEngine(devices, engine) {
  return (devices || []).filter(
    (d) => d?.status === '在线' && deviceSupportsEngine(d, engine)
  )
}

export function filterWebRunnerDevices(devices) {
  return filterOnlineDevicesByEngine(devices, 'web')
}

export function filterAppRunnerDevices(devices) {
  return filterOnlineDevicesByEngine(devices, 'app')
}
