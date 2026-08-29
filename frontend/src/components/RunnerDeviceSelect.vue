<template>
  <el-select
    :model-value="modelValue"
    :placeholder="placeholder"
    :clearable="clearable"
    :disabled="disabled"
    :style="selectStyle"
    filterable
    @update:model-value="emit('update:modelValue', $event)"
  >
    <el-option
      v-for="device in deviceList"
      :key="device.id"
      :label="deviceLabel(device)"
      :value="device.id"
    >
      <div class="runner-device-option">
        <span class="name">{{ device.name || device.username }}</span>
        <span class="ip">{{ device.ip }}</span>
        <el-tag
          v-for="eng in deviceEngineTypes(device)"
          :key="eng"
          size="small"
          type="info"
          effect="plain"
        >{{ eng }}</el-tag>
        <el-tag type="success" size="small">在线</el-tag>
      </div>
    </el-option>
  </el-select>
</template>

<script setup>
import { onMounted, ref, watch } from 'vue'
import { deviceApi } from '@/api'
import { deviceEngineTypes, filterOnlineDevicesByEngine } from '@/utils/runnerDevice'

const props = defineProps({
  modelValue: { type: [String, Number], default: '' },
  projectId: { type: Number, default: null },
  /** web | app | any */
  engine: { type: String, default: 'any' },
  placeholder: { type: String, default: '请选择在线 Runner 设备' },
  clearable: { type: Boolean, default: true },
  disabled: { type: Boolean, default: false },
  selectStyle: { type: [String, Object], default: () => ({ width: '100%' }) },
  autoPickFirst: { type: Boolean, default: true }
})

const emit = defineEmits(['update:modelValue', 'loaded'])

const deviceList = ref([])
const loading = ref(false)

const deviceLabel = (device) => {
  const name = device.name || device.username || device.id
  const engines = deviceEngineTypes(device).join('/')
  return `${name} (${device.ip || '—'}) · ${engines}`
}

const filterDevices = (rows) => {
  const online = (rows || []).filter((d) => d?.status === '在线' || d?.status === 'online')
  if (props.engine === 'web') return filterOnlineDevicesByEngine(online, 'web')
  if (props.engine === 'app') return filterOnlineDevicesByEngine(online, 'app')
  return online.filter(
    (d) =>
      filterOnlineDevicesByEngine([d], 'web').length ||
      filterOnlineDevicesByEngine([d], 'app').length
  )
}

const loadDevices = async () => {
  if (!props.projectId) {
    deviceList.value = []
    return
  }
  loading.value = true
  try {
    const res = await deviceApi.getList({ page: 1, size: 200, status: '在线' })
    deviceList.value = filterDevices(res.data || [])
    emit('loaded', deviceList.value)
    if (props.autoPickFirst && !props.modelValue && deviceList.value.length) {
      emit('update:modelValue', deviceList.value[0].id)
    }
  } catch {
    deviceList.value = []
  } finally {
    loading.value = false
  }
}

watch(() => props.projectId, () => loadDevices(), { immediate: true })
onMounted(loadDevices)

defineExpose({ reload: loadDevices, deviceList, loading })
</script>

<style scoped>
.runner-device-option {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.runner-device-option .name {
  font-weight: 500;
}
.runner-device-option .ip {
  color: #909399;
  font-size: 12px;
}
</style>
