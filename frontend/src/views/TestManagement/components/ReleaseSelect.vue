<template>
  <el-select
    :model-value="modelValue"
    filterable
    clearable
    :placeholder="placeholder"
    :style="{ width }"
    :loading="loading"
    :disabled="disabled"
    @update:model-value="emit('update:modelValue', $event)"
    @visible-change="onVisible"
  >
    <el-option
      v-for="r in releases"
      :key="r.id"
      :label="optionLabel(r)"
      :value="r.id"
    />
  </el-select>
</template>

<script setup>
import { ref, watch } from 'vue'
import { testReleaseApi } from '@/api/testManagement'
import { releaseStatusLabel } from '@/utils/testReleaseStatus'

const props = defineProps({
  modelValue: { type: Number, default: null },
  projectId: { type: Number, required: true },
  placeholder: { type: String, default: '选择版本' },
  width: { type: String, default: '240px' },
  /** 为 true 时排除已发布/已归档（新建缺陷等场景） */
  excludeTerminal: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false }
})
const emit = defineEmits(['update:modelValue', 'loaded'])

const releases = ref([])
const loading = ref(false)
const loadedFor = ref(null)

const optionLabel = (r) => {
  const st = releaseStatusLabel(r.status)
  return `${r.release_key || r.id} · ${r.name || ''}（${st}）`
}

const load = async (force = false) => {
  if (!props.projectId) return
  if (!force && loadedFor.value === props.projectId) return
  loading.value = true
  try {
    const res = await testReleaseApi.list({ project_id: props.projectId })
    let list = res.data?.data || []
    if (props.excludeTerminal) {
      list = list.filter((r) => !['released', 'archived'].includes(r.status))
    }
    releases.value = list
    loadedFor.value = props.projectId
    emit('loaded', list)
  } finally {
    loading.value = false
  }
}

const onVisible = (v) => {
  if (v) load()
}

watch(
  () => props.projectId,
  () => {
    loadedFor.value = null
    releases.value = []
    if (props.projectId) load(true)
  },
  { immediate: true }
)

defineExpose({ load, releases })
</script>
