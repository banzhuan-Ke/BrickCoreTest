<template>
  <div class="knowledge-digest-view">
    <template v-if="collapseSections.length">
      <div v-if="introSection" class="digest-intro">
        <MarkdownReport :content="introSection" compact />
      </div>
      <el-collapse v-model="openSections" class="digest-sections">
        <el-collapse-item
          v-for="(sec, idx) in collapseSections"
          :key="idx"
          :name="String(idx)"
          :title="sec.title"
        >
          <MarkdownReport :content="sec.body" />
        </el-collapse-item>
      </el-collapse>
    </template>
    <div v-else class="digest-body">
      <MarkdownReport :content="content" />
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import MarkdownReport from '@/components/MarkdownReport.vue'
import { splitDigestSections } from '@/modules/knowledge/utils/chunkTextFormat.js'

const props = defineProps({
  content: { type: String, default: '' }
})

const openSections = ref([])

const parsed = computed(() => splitDigestSections(props.content))

const introSection = computed(() => {
  const first = parsed.value[0]
  return first?.intro || ''
})

const collapseSections = computed(() =>
  parsed.value.filter((s) => s.title && s.body)
)

watch(
  () => props.content,
  () => {
    openSections.value = collapseSections.value.slice(0, 3).map((_, i) => String(i))
  },
  { immediate: true }
)
</script>

<style scoped>
.knowledge-digest-view {
  width: 100%;
}
.digest-intro {
  margin-bottom: 12px;
  padding: 12px 14px;
  border-radius: 8px;
  background: var(--el-color-primary-light-9);
  border: 1px solid var(--el-color-primary-light-7);
  font-size: 13px;
}
.digest-sections {
  border: none;
}
.digest-sections :deep(.el-collapse-item__header) {
  font-weight: 600;
  font-size: 13px;
  line-height: 1.5;
  padding-right: 8px;
}
.digest-sections :deep(.el-collapse-item__content) {
  padding-bottom: 12px;
}
.digest-body {
  width: 100%;
}
</style>
