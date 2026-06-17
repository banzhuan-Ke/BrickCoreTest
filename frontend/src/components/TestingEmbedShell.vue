<template>
  <div v-if="inline" class="embed-detail-panel">
    <slot />
  </div>
  <el-drawer
    v-else
    v-model="drawerOpen"
    :size="drawerSize"
    :modal="true"
    :with-header="withHeader"
    :destroy-on-close="destroyOnClose"
  >
    <template v-if="withHeader && $slots.header" #header>
      <slot name="header" />
    </template>
    <slot />
  </el-drawer>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  inline: { type: Boolean, default: false },
  modelValue: { type: Boolean, default: false },
  drawerSize: { type: String, default: '90%' },
  withHeader: { type: Boolean, default: true },
  destroyOnClose: { type: Boolean, default: false }
})

const emit = defineEmits(['update:modelValue'])

const drawerOpen = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v)
})
</script>

<style scoped>
.embed-detail-panel {
  width: 100%;
  min-height: 120px;
}
</style>
