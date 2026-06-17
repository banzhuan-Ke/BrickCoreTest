<template>
  <el-select
    :model-value="modelValue"
    placeholder="请选择运行环境"
    filterable
    clearable
    style="width: 100%"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <el-option
      v-for="env in envList"
      :key="env.id"
      :label="env.name"
      :value="env.id"
    >
      <div class="ui-env-option">
        <span class="ui-env-option__name">{{ env.name }}</span>
        <span class="ui-env-option__host">{{ env.host }}</span>
      </div>
    </el-option>
  </el-select>
</template>

<script setup>
import { computed } from 'vue'
import { ProjectStore } from '@/stores/module/ProjectStore'

defineProps({
  modelValue: {
    type: [String, Number],
    default: '',
  },
})

defineEmits(['update:modelValue'])

const proStore = ProjectStore()
const envList = computed(() => proStore.envList || [])
</script>

<style scoped lang="scss">
.ui-env-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
}

.ui-env-option__name {
  flex-shrink: 0;
  font-weight: 500;
}

.ui-env-option__host {
  flex: 1;
  min-width: 0;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  text-align: right;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
