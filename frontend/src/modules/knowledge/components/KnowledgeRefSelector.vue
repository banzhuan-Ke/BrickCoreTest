<template>
  <div v-if="false" />
</template>

<script setup>
/**
 * CE stub：迭代资料库引用选择器（开发测试中，后续放出）。
 */
defineProps({
  modelValue: { type: [Array, Object, String], default: () => [] },
  projectId: { type: [Number, String], default: null },
  scene: { type: String, default: '' },
  disabled: { type: Boolean, default: false },
})
defineEmits(['update:modelValue'])
</script>
