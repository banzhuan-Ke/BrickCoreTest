<template>
  <el-collapse v-model="activeNames" class="var-preview-panel">
    <el-collapse-item title="变量预览（执行前）" name="preview">
      <div v-loading="loading" class="preview-body">
        <p v-if="!envId && !projectId" class="preview-hint">请选择执行环境后查看可用变量</p>
        <template v-else>
          <p class="preview-hint">优先级：项目变量 &lt; 环境变量 &lt; 额外传入</p>
          <el-table v-if="variableRows.length" :data="variableRows" size="small" border max-height="240">
            <el-table-column label="变量名" prop="key" width="140" show-overflow-tooltip />
            <el-table-column label="解析值" prop="value" min-width="160" show-overflow-tooltip />
            <el-table-column label="来源" prop="source" width="80" />
          </el-table>
          <el-empty v-else description="暂无可用变量" :image-size="48" />

          <div v-if="sampleRows.length" class="sample-block">
            <div class="sample-title">示例替换（基于当前环境变量自动生成）</div>
            <el-table :data="sampleRows" size="small" border>
              <el-table-column label="原始" prop="original" min-width="140" show-overflow-tooltip />
              <el-table-column label="替换后" prop="replaced" min-width="160" show-overflow-tooltip />
              <el-table-column label="说明" width="100" align="center">
                <template #default="{ row }">
                  <el-tag v-if="row.unchanged" type="info" size="small">未匹配</el-tag>
                  <el-tag v-else type="success" size="small">已替换</el-tag>
                </template>
              </el-table-column>
            </el-table>
            <p v-if="hasUnmatchedSamples" class="preview-hint sample-note">
              「未匹配」表示占位符在当前变量中不存在，执行时仍会保留原文。
            </p>
          </div>
        </template>
      </div>
    </el-collapse-item>
  </el-collapse>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { httpCaseApi } from '@/api/modules/http'

const props = defineProps({
  envId: { type: Number, default: null },
  projectId: { type: Number, default: null },
  extraVariables: { type: Object, default: () => ({}) },
  samples: { type: Array, default: () => [] },
})

const proStore = ProjectStore()
const loading = ref(false)
const activeNames = ref(['preview'])
const previewData = ref({ variables: {}, samples: [] })

const resolvedProjectId = computed(() => props.projectId || proStore.projectInfo?.id || null)

const variableRows = computed(() => {
  const vars = previewData.value.variables || {}
  const projKeys = new Set(Object.keys(proStore.projectInfo?.global_vars || {}))
  const env = props.envId ? proStore.envList.find((e) => e.id === props.envId) : null
  const envKeys = new Set(Object.keys(env?.global_vars || {}))
  return Object.entries(vars).map(([key, value]) => ({
    key,
    value: value === null || value === undefined ? '' : String(value),
    source: props.extraVariables?.[key] !== undefined ? '传入' : envKeys.has(key) ? '环境' : projKeys.has(key) ? '项目' : '动态',
  }))
})

const sampleRows = computed(() => previewData.value.samples || [])

const hasUnmatchedSamples = computed(() => sampleRows.value.some((row) => row.unchanged))

async function loadPreview() {
  if (!props.envId && !resolvedProjectId.value) {
    previewData.value = { variables: {}, samples: [] }
    return
  }
  loading.value = true
  try {
    const res = await httpCaseApi.previewVariables({
      env_id: props.envId || undefined,
      project_id: resolvedProjectId.value || undefined,
      extra_variables: props.extraVariables || {},
      samples: props.samples?.length ? props.samples : [],
    })
    previewData.value = res.data || { variables: {}, samples: [] }
  } catch {
    previewData.value = { variables: {}, samples: [] }
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.envId, resolvedProjectId.value, props.extraVariables, props.samples],
  () => {
    if (props.envId || resolvedProjectId.value) {
      loadPreview()
    }
  },
  { deep: true, immediate: true }
)

defineExpose({ reload: loadPreview })
</script>

<style scoped lang="scss">
.var-preview-panel {
  margin-top: 8px;
}

.preview-body {
  min-height: 40px;
}

.preview-hint {
  margin: 0 0 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.sample-block {
  margin-top: 12px;
}

.sample-title {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 6px;
}

.sample-note {
  margin-top: 6px;
  margin-bottom: 0;
}
</style>
