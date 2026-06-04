import { ref } from 'vue'
import { deviceApi } from '@/api/modules/sys'

function parseDeviceResponse(res) {
  if (!res || res.status !== 200) {
    return { list: [], error: res?.data?.detail || `请求失败 (${res?.status || 'unknown'})` }
  }
  const raw = res.data
  if (Array.isArray(raw)) return { list: raw, error: null }
  if (Array.isArray(raw?.data)) return { list: raw.data, error: null }
  if (Array.isArray(raw?.list)) return { list: raw.list, error: null }
  return { list: [], error: '设备列表格式异常' }
}

/**
 * 加载在线 Runner 设备（与用例运行页逻辑一致，含降级与错误提示）
 */
export function useOnlineDevices() {
  const onlineDevices = ref([])
  const loadingDevices = ref(false)
  const deviceLoadError = ref('')

  const loadOnlineDevices = async () => {
    loadingDevices.value = true
    deviceLoadError.value = ''
    try {
      let { list, error } = parseDeviceResponse(await deviceApi.getList({ status: '在线' }))
      if (!list.length) {
        const fallback = parseDeviceResponse(await deviceApi.getList())
        list = fallback.list.filter(d => d.status === '在线')
        if (!list.length && fallback.error) error = fallback.error
      }
      onlineDevices.value = list
      if (!list.length) {
        deviceLoadError.value =
          error ||
          '暂无在线 Runner。请在本机 runner 目录切换配置（start-local.bat / start-online.bat）后运行 python main.py，并确保设备管理页显示「在线」'
      }
      return list
    } catch (e) {
      onlineDevices.value = []
      deviceLoadError.value =
        e.response?.data?.detail ||
        '加载执行设备失败，请确认账号有 device:view 权限且后端服务正常'
      return []
    } finally {
      loadingDevices.value = false
    }
  }

  return { onlineDevices, loadingDevices, deviceLoadError, loadOnlineDevices }
}
