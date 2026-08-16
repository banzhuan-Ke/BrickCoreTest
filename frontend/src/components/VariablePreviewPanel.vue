<template>
  <el-collapse v-model="activeNames" class="var-preview-panel">
    <el-collapse-item title="变量预览（执行前）" name="preview">
      <div v-loading="loading" class="preview-body">
        <p v-if="!envId && !projectId" class="preview-hint">请选择执行环境后查看可用变量</p>
        <template v-else>
          <p class="preview-hint">优先级：项目变量 &lt; 环境变量 &lt; 数据工厂 &lt; 传入 &lt; Token 授权</p>
          <p class="preview-hint sample-note">预览仅读取已有授权缓存，不会自动登录；缓存为空请到「Token 授权」刷新。</p>
          <el-table v-if="variableRows.length" :data="variableRows" size="small" border max-height="240">
            <el-table-column label="变量名" prop="key" width="120" show-overflow-tooltip />
            <el-table-column label="描述" prop="description" min-width="120" show-overflow-tooltip />
            <el-table-column label="解析值" prop="value" min-width="140" show-overflow-tooltip />
            <el-table-column label="来源" prop="source" width="72" />
          </el-table>
          <el-empty v-else description="暂无可用变量" :image-size="48" />
          <p v-if="previewData.auth_error" class="preview-hint sample-note">
            Token 授权：{{ previewData.auth_error }}
          </p>

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
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { httpCaseApi } from '@/api/modules/http'
import { getVarDescription, BUILTIN_VAR_HINTS } from '@/utils/globalVars.js'

const props = defineProps({
  envId: { type: Number, default: null },
  projectId: { type: Number, default: null },
  extraVariables: { type: Object, default: () => ({}) },
  samples: { type: Array, default: () => [] },
})

const proStore = ProjectStore()
const loading = ref(false)
const activeNames = ref(['preview'])
const previewData = ref({ variables: {}, samples: [], auth_error: null })
const builtinHintKeys = new Set(BUILTIN_VAR_HINTS.map((item) => item.key || item.name || item).filter(Boolean))

const resolvedProjectId = computed(() => props.projectId || proStore.projectInfo?.id || null)

const variableRows = computed(() => {
  const vars = previewData.value.variables || {}
  const projVars = proStore.projectInfo?.global_vars || {}
  const projKeys = new Set(Object.keys(projVars))
  const env = props.envId ? proStore.envList.find((e) => e.id === props.envId) : null
  const envVars = env?.global_vars || {}
  const envKeys = new Set(Object.keys(envVars))
  return Object.entries(vars).map(([key, value]) => {
    let description = ''
    if (envKeys.has(key)) description = getVarDescription(envVars, key)
    else if (projKeys.has(key)) description = getVarDescription(projVars, key)
    let source = '其它'
    if (props.extraVariables?.[key] !== undefined) source = '传入'
    else if (envKeys.has(key)) source = '环境'
    else if (projKeys.has(key)) source = '项目'
    else if (String(key).startsWith('df:')) source = '工厂'
    else if (builtinHintKeys.has(key)) source = '动态'
    else source = '授权'
    return {
      key,
      description: description || '—',
      value: value === null || value === undefined ? '' : String(value),
      source,
    }
  })
})

const sampleRows = computed(() => previewData.value.samples || [])

const hasUnmatchedSamples = computed(() => sampleRows.value.some((row) => row.unchanged))

let previewTimer = null
let previewSeq = 0

async function loadPreview() {
  if (!props.envId && !resolvedProjectId.value) {
    previewData.value = { variables: {}, samples: [], auth_error: null }
    return
  }
  const seq = ++previewSeq
  loading.value = true
  try {
    const res = await httpCaseApi.previewVariables({
      env_id: props.envId || undefined,
      project_id: resolvedProjectId.value || undefined,
      extra_variables: props.extraVariables || {},
      samples: props.samples?.length ? props.samples : [],
    })
    if (seq !== previewSeq) return
    previewData.value = {
      variables: {},
      samples: [],
      auth_error: null,
      ...(res.data || {}),
    }
  } catch {
    if (seq !== previewSeq) return
    previewData.value = { variables: {}, samples: [], auth_error: null }
  } finally {
    if (seq === previewSeq) loading.value = false
  }
}

function schedulePreview() {
  if (previewTimer) clearTimeout(previewTimer)
  previewTimer = setTimeout(() => {
    previewTimer = null
    if (props.envId || resolvedProjectId.value) {
      loadPreview()
    }
  }, 280)
}

watch(
  () => [props.envId, resolvedProjectId.value, props.extraVariables, props.samples],
  () => schedulePreview(),
  { deep: true, immediate: true }
)

onBeforeUnmount(() => {
  if (previewTimer) clearTimeout(previewTimer)
  previewSeq += 1
})

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
