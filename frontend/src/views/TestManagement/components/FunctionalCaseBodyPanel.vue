<template>
  <div class="case-body-panel" v-loading="loading">
    <template v-if="displayCase">
      <div class="case-head" v-if="showTitle">
        <span class="case-id" v-if="displayCase.id">#{{ displayCase.id }}</span>
        <span class="case-title">{{ displayCase.title || displayCase.case_title || '—' }}</span>
        <el-tag v-if="displayCase.module || displayCase.case_module" size="small" effect="plain">
          {{ displayCase.module || displayCase.case_module }}
        </el-tag>
      </div>
      <div class="field-block">
        <div class="field-label">前置条件</div>
        <div class="field-value pre">{{ displayCase.precondition || displayCase.case_precondition || '—' }}</div>
      </div>
      <div class="steps-grid">
        <div class="field-block">
          <div class="field-label">步骤</div>
          <div class="field-value steps">{{ stepsText || '—' }}</div>
        </div>
        <div class="field-block">
          <div class="field-label">预期</div>
          <div class="field-value steps">{{ expectsText || '—' }}</div>
        </div>
      </div>
      <div v-if="displayCase.source_requirement_id" class="req-link">
        来源需求：
        <router-link :to="`/ai-testing/requirements/${displayCase.source_requirement_id}`">
          REQ-{{ displayCase.source_requirement_id }}
        </router-link>
      </div>
    </template>
    <el-empty v-else-if="!loading" description="暂无用例正文" />
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { aiFunctionalCaseApi } from '@/api/modules/ai.js'
import { formatStepsText, formatExpectsText } from '@/utils/formatCaseSteps.js'

const props = defineProps({
  /** 直接传入用例对象（含 precondition / steps / title） */
  caseData: { type: Object, default: null },
  /** 或通过 ID 拉取 */
  functionalCaseId: { type: Number, default: null },
  projectId: { type: Number, default: null },
  showTitle: { type: Boolean, default: true }
})

const loading = ref(false)
const fetched = ref(null)

const displayCase = computed(() => props.caseData || fetched.value)

const stepsText = computed(() => formatStepsText(displayCase.value?.steps || displayCase.value?.case_steps))
const expectsText = computed(() => formatExpectsText(displayCase.value?.steps || displayCase.value?.case_steps))

const loadById = async () => {
  const id = props.functionalCaseId
  const pid = props.projectId
  if (!id || !pid || props.caseData) {
    fetched.value = null
    return
  }
  loading.value = true
  try {
    const res = await aiFunctionalCaseApi.get(id, pid)
    fetched.value = res.data?.data || null
  } catch {
    fetched.value = null
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.functionalCaseId, props.projectId, props.caseData],
  () => loadById(),
  { immediate: true }
)
</script>

<style scoped>
.case-body-panel {
  min-height: 48px;
}
.case-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.case-id {
  color: #909399;
  font-size: 13px;
}
.case-title {
  font-weight: 600;
  font-size: 15px;
  color: #303133;
}
.field-block {
  margin-bottom: 12px;
}
.field-label {
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}
.field-value {
  font-size: 13px;
  color: #303133;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
  padding: 10px 12px;
  background: #f9fafb;
  border: 1px solid #eaecf0;
  border-radius: 8px;
}
.steps-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
@media (max-width: 720px) {
  .steps-grid {
    grid-template-columns: 1fr;
  }
}
.req-link {
  margin-top: 8px;
  font-size: 12px;
  color: #606266;
}
.req-link a {
  color: var(--el-color-primary);
  text-decoration: none;
}
</style>
