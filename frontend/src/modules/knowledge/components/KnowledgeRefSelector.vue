<template>
  <el-alert
    type='info'
    :closable='false'
    show-icon
    title='????????'
    description='CE ??????????????'
  />
</template>
<script setup>
defineProps({
  modelValue: {
    type: Object,
    default: () => ({ folder_ids: [], document_ids: [] })
  }
})
defineEmits(['update:modelValue'])
</script>
