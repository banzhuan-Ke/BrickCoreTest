<template>
  <div v-if="executionId && canShowFailureAnalysis" class="case-failure-ai">
    <div v-if="analysis?.root_cause" class="case-failure-ai-summary">
      <div class="case-failure-ai-head">
        <span class="case-failure-ai-label">AI 根因分析</span>
        <el-tag v-if="analysis.cached" size="small" type="info">历史分析</el-tag>
        <el-tag v-if="analysis.vision_used" size="small" type="success">含截图识图</el-tag>
      </div>
      <p class="case-failure-ai-root">{{ analysis.root_cause }}</p>
      <ul v-if="topSuggestions.length" class="case-failure-ai-list">
        <li v-for="(item, idx) in topSuggestions" :key="'s' + idx">{{ item }}</li>
      </ul>
    </div>
    <div class="case-failure-ai-actions">
      <el-button size="small" type="warning" plain :loading="loading" @click.stop="openDrawer">
        {{ analysis?.root_cause ? '查看完整 AI 分析' : 'AI 分析失败原因' }}
      </el-button>
    </div>
    <FailureAnalyzer
      v-model="drawerVisible"
      :target-type="targetType"
      :target-id="executionId"
    />
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { aiAnalyzeApi } from '@/api/modules/ai.js'
import FailureAnalyzer from '@/views/AI/components/FailureAnalyzer.vue'
import { useFailureAnalysisGate } from '@/composables/useFailureAnalysisGate.js'

const props = defineProps({
  executionId: { type: Number, default: null },
  targetType: { type: String, default: 'ui' },
  projectId: { type: [Number, String], default: null },
  autoExpand: { type: Boolean, default: false }
})

const emit = defineEmits(['loaded'])

const { canShowFailureAnalysis } = useFailureAnalysisGate(ref(null), { syncProject: true })

const loading = ref(false)
const analysis = ref(null)
const drawerVisible = ref(false)

const topSuggestions = computed(() => (analysis.value?.suggestions || []).slice(0, 3))

async function loadAnalysis() {
  analysis.value = null
  if (!props.executionId || !props.projectId || !canShowFailureAnalysis.value) {
    emit('loaded', null)
    return
  }
  loading.value = true
  try {
    const res = await aiAnalyzeApi.getByTarget(
      props.targetType,
      props.executionId,
      props.projectId
    )
    if (res.data?.code === 200 && res.data.data?.root_cause) {
      analysis.value = res.data.data
    }
  } catch {
    analysis.value = null
  } finally {
    loading.value = false
    emit('loaded', analysis.value)
  }
}

function openDrawer() {
  if (!props.executionId) return
  drawerVisible.value = true
}

watch(
  () => [props.executionId, props.projectId, canShowFailureAnalysis.value],
  () => loadAnalysis(),
  { immediate: true }
)

watch(drawerVisible, (open, prev) => {
  if (!open && prev) loadAnalysis()
})
</script>

<style scoped>
.case-failure-ai {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed var(--el-border-color-lighter);
}
.case-failure-ai-summary {
  margin-bottom: 10px;
}
.case-failure-ai-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 6px;
}
.case-failure-ai-label {
  font-size: 13px;
  font-weight: 600;
  color: #e6a23c;
}
.case-failure-ai-root {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: #f56c6c;
}
.case-failure-ai-list {
  margin: 8px 0 0;
  padding-left: 18px;
  font-size: 12px;
  line-height: 1.55;
  color: var(--el-text-color-regular);
}
.case-failure-ai-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
</style>
