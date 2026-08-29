<template>
  <el-select
    :model-value="modelValue"
    filterable
    clearable
    :multiple="multiple"
    :collapse-tags="multiple"
    :collapse-tags-tooltip="multiple"
    :placeholder="placeholder"
    :disabled="disabled"
    :style="{ width: width }"
    @update:model-value="emit('update:modelValue', $event)"
    @visible-change="onVisible"
  >
    <el-option
      v-for="m in members"
      :key="m.user_id"
      :label="memberLabel(m)"
      :value="m.user_id"
    />
  </el-select>
</template>

<script setup>
import { ref, watch } from 'vue'
import http from '@/api/index'

const props = defineProps({
  modelValue: { type: [Number, Array], default: null },
  projectId: { type: Number, required: true },
  placeholder: { type: String, default: '选择成员' },
  width: { type: String, default: '220px' },
  multiple: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false }
})
const emit = defineEmits(['update:modelValue'])

const members = ref([])
const loadedFor = ref(null)

const memberLabel = (m) => {
  const name = m.nickname || m.username || `用户 ${m.user_id}`
  return m.user_id ? `${name} (#${m.user_id})` : name
}

const load = async (force = false) => {
  if (!props.projectId) return
  if (!force && loadedFor.value === props.projectId) return
  const res = await http.projectApi.getMembers(props.projectId, { page: 1, size: 200 })
  members.value = res.data?.data?.items || res.data?.data || []
  loadedFor.value = props.projectId
}

const onVisible = (v) => {
  if (v) load()
}

watch(
  () => props.projectId,
  () => {
    loadedFor.value = null
    members.value = []
    if (props.projectId) load(true)
  },
  { immediate: true }
)
</script>
