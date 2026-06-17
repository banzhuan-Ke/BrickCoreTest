<template>
  <div class="test-file-ref-tags">
    <template v-if="refs?.total">
      <el-tag v-for="item in previewTags" :key="item.key" size="small" type="info" class="ref-tag">
        {{ item.label }}
      </el-tag>
      <el-button
        v-if="refs.total > previewTags.length"
        type="primary"
        link
        size="small"
        @click="emit('detail')"
      >
        查看全部 ({{ refs.total }})
      </el-button>
      <el-button
        v-else-if="refs.total"
        type="primary"
        link
        size="small"
        @click="emit('detail')"
      >
        详情
      </el-button>
    </template>
    <span v-else class="no-ref">无</span>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  refs: { type: Object, default: () => ({ total: 0 }) },
  mode: { type: String, default: 'ui' },
  previewLimit: { type: Number, default: 4 },
})

const emit = defineEmits(['detail'])

const previewTags = computed(() => {
  const refs = props.refs || {}
  const tags = []
  if (props.mode === 'ui') {
    refs.cases?.forEach((c) => tags.push({ key: `case-${c.id}`, label: `用例: ${c.name}` }))
    refs.suites?.forEach((s) => tags.push({ key: `suite-${s.id}`, label: `套件: ${s.name}` }))
    refs.fragments?.forEach((f) => tags.push({ key: `frag-${f.id}`, label: `片段: ${f.name}` }))
  } else {
    refs.apis?.forEach((a) => tags.push({ key: `api-${a.id}`, label: `接口: ${a.name}` }))
    refs.cases?.forEach((c) => tags.push({ key: `case-${c.id}`, label: `用例: ${c.name}` }))
  }
  return tags.slice(0, props.previewLimit)
})
</script>

<style scoped lang="scss">
.test-file-ref-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
}
.ref-tag {
  max-width: 160px;
}
.ref-tag :deep(.el-tag__content) {
  overflow: hidden;
  text-overflow: ellipsis;
}
.no-ref {
  color: var(--el-text-color-placeholder);
  font-size: 13px;
}
</style>
