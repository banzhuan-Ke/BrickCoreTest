<template>
  <div v-if="visible" class="csv-perf-hint">
    <el-alert type="warning" :closable="false" show-icon class="csv-perf-hint__alert">
      <template #title>
        <span>检测到 CSV 引用（{{ columnPreview }}）</span>
      </template>
      <div class="csv-perf-hint__body">
        <p>
          <code v-pre>${{csv.列名}}</code> /
          <code v-pre>${{dt:md5|text=@csv.列名}}</code>
          仅在<strong>压测场景执行</strong>时由场景绑定的 CSV 数据集自动注入；接口调试与单条用例执行默认不会注入。
        </p>
        <p v-if="loadingContexts" class="csv-perf-hint__muted">正在查找关联场景与数据集…</p>
        <p v-else-if="datasets.length" class="csv-perf-hint__scenes">
          项目 CSV 数据集：
          <router-link
            v-for="d in datasets.slice(0, 5)"
            :key="d.id"
            class="csv-perf-hint__link"
            to="/perf-csv-datasets"
          >{{ d.name }}（{{ d.row_count }} 行）</router-link>
        </p>
        <p v-if="csvScenes.length" class="csv-perf-hint__scenes">
          关联且已绑 CSV 的场景：
          <router-link
            v-for="s in csvScenes.slice(0, 5)"
            :key="s.id"
            class="csv-perf-hint__link"
            :to="`/perf-scene/edit/${s.id}`"
          >{{ s.name }}（{{ s.row_count }} 行）</router-link>
        </p>
        <p v-else-if="loadedContexts && !datasets.length" class="csv-perf-hint__muted">
          请到
          <router-link class="csv-perf-hint__link" to="/perf-csv-datasets">CSV 数据集</router-link>
          或
          <router-link class="csv-perf-hint__link" to="/perf-scenes">性能测试场景</router-link>
          上传 CSV 并绑定后再压测。
        </p>
      </div>
    </el-alert>

    <el-collapse v-if="showTryRun" v-model="tryRunOpen" class="csv-try-run">
      <el-collapse-item name="try">
        <template #title>
          <span class="csv-try-run__title">用 CSV 试跑一行（非默认）</span>
        </template>
        <p class="csv-try-run__hint">
          选择数据集或关联场景与行号后，本次调试/执行会注入该行（含 <code>列名</code> 与 <code>csv.列名</code>）；正式压测仍走场景 CSV 策略。
        </p>
        <el-form label-width="88px" size="small" class="csv-try-run__form">
          <el-form-item label="启用">
            <el-switch v-model="enabledLocal" />
          </el-form-item>
          <template v-if="enabledLocal">
            <el-form-item label="数据来源" required>
              <el-radio-group v-model="trySourceLocal" size="small">
                <el-radio-button label="dataset">CSV 数据集</el-radio-button>
                <el-radio-button label="scene">压测场景</el-radio-button>
              </el-radio-group>
            </el-form-item>
            <el-form-item v-if="trySourceLocal === 'dataset'" label="数据集" required>
              <el-select
                v-model="datasetIdLocal"
                filterable
                clearable
                placeholder="选择项目 CSV 数据集"
                style="width: 100%"
                :loading="loadingContexts"
              >
                <el-option
                  v-for="d in datasets"
                  :key="d.id"
                  :label="`${d.name}（${d.row_count} 行）`"
                  :value="d.id"
                />
              </el-select>
            </el-form-item>
            <el-form-item v-else label="压测场景" required>
              <el-select
                v-model="sceneIdLocal"
                filterable
                clearable
                placeholder="选择已绑 CSV 的场景"
                style="width: 100%"
                :loading="loadingContexts"
              >
                <el-option
                  v-for="s in csvScenes"
                  :key="s.id"
                  :label="`${s.name}（${s.row_count} 行）`"
                  :value="s.id"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="行号" required>
              <el-input-number
                v-model="rowIndexLocal"
                :min="0"
                :max="Math.max(0, (selectedSource?.row_count || 1) - 1)"
                controls-position="right"
              />
              <span class="csv-perf-hint__muted" style="margin-left: 8px">
                0 起，共 {{ selectedSource?.row_count ?? 0 }} 行
              </span>
            </el-form-item>
            <el-form-item v-if="previewRow" label="预览">
              <pre class="csv-try-run__preview">{{ previewRowText }}</pre>
            </el-form-item>
          </template>
        </el-form>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { listCsvColumnRefs } from '@/utils/csvVarRefs'
import { perfSceneApi } from '@/api/modules/perf'

const props = defineProps({
  source: { type: [Object, String, Array], default: null },
  columns: { type: Array, default: null },
  projectId: { type: [Number, String], default: null },
  caseId: { type: [Number, String], default: null },
  apiId: { type: [Number, String], default: null },
  showTryRun: { type: Boolean, default: false },
  enabled: { type: Boolean, default: false },
  trySource: { type: String, default: 'dataset' },
  csvSceneId: { type: [Number, String], default: null },
  csvDatasetId: { type: [Number, String], default: null },
  csvRowIndex: { type: Number, default: 0 },
})

const emit = defineEmits([
  'update:enabled',
  'update:trySource',
  'update:csvSceneId',
  'update:csvDatasetId',
  'update:csvRowIndex',
])

const loadingContexts = ref(false)
const loadedContexts = ref(false)
const contexts = ref({ csv_scenes: [], scenes: [], datasets: [] })
const tryRunOpen = ref([])

const detectedColumns = computed(() => {
  if (Array.isArray(props.columns) && props.columns.length) {
    return props.columns.map(String)
  }
  return listCsvColumnRefs(props.source)
})

const visible = computed(() => detectedColumns.value.length > 0)

const columnPreview = computed(() => {
  const cols = detectedColumns.value
  if (!cols.length) return ''
  const shown = cols.slice(0, 4).map((c) => `csv.${c}`).join('、')
  return cols.length > 4 ? `${shown}…` : shown
})

const csvScenes = computed(() => contexts.value.csv_scenes || [])
const datasets = computed(() => contexts.value.datasets || [])

const enabledLocal = computed({
  get: () => props.enabled,
  set: (v) => emit('update:enabled', !!v),
})

const trySourceLocal = computed({
  get: () => props.trySource || 'dataset',
  set: (v) => {
    emit('update:trySource', v)
    if (v === 'dataset') emit('update:csvSceneId', null)
    else emit('update:csvDatasetId', null)
  },
})

const sceneIdLocal = computed({
  get: () => props.csvSceneId,
  set: (v) => emit('update:csvSceneId', v ?? null),
})

const datasetIdLocal = computed({
  get: () => props.csvDatasetId,
  set: (v) => emit('update:csvDatasetId', v ?? null),
})

const rowIndexLocal = computed({
  get: () => props.csvRowIndex ?? 0,
  set: (v) => emit('update:csvRowIndex', Number(v) || 0),
})

const selectedDataset = computed(() =>
  datasets.value.find((d) => Number(d.id) === Number(props.csvDatasetId))
)

const selectedScene = computed(() =>
  csvScenes.value.find((s) => Number(s.id) === Number(props.csvSceneId))
)

const selectedSource = computed(() =>
  trySourceLocal.value === 'dataset' ? selectedDataset.value : selectedScene.value
)

const previewRow = computed(() => {
  const src = selectedSource.value
  if (!src?.preview_rows?.length) return null
  const idx = Math.min(Math.max(0, props.csvRowIndex || 0), src.preview_rows.length - 1)
  if ((props.csvRowIndex || 0) < src.preview_rows.length) {
    return src.preview_rows[idx]
  }
  return src.preview_rows[0]
})

const previewRowText = computed(() => {
  if (!previewRow.value) return ''
  try {
    return JSON.stringify(previewRow.value, null, 2)
  } catch {
    return String(previewRow.value)
  }
})

async function loadContexts() {
  const pid = Number(props.projectId)
  if (!pid || !visible.value) {
    contexts.value = { csv_scenes: [], scenes: [], datasets: [] }
    loadedContexts.value = false
    return
  }
  const params = { project_id: pid, preview_limit: 5 }
  if (props.caseId) params.case_id = Number(props.caseId)
  if (props.apiId) params.api_id = Number(props.apiId)

  loadingContexts.value = true
  try {
    const res = await perfSceneApi.listCsvContexts(params)
    contexts.value = res?.data || res || { csv_scenes: [], scenes: [], datasets: [] }
    loadedContexts.value = true
  } catch {
    contexts.value = { csv_scenes: [], scenes: [], datasets: [] }
    loadedContexts.value = true
  } finally {
    loadingContexts.value = false
  }
}

watch(
  () => [visible.value, props.projectId, props.caseId, props.apiId],
  () => {
    loadContexts()
  },
  { immediate: true }
)

watch(enabledLocal, (on) => {
  if (on && !tryRunOpen.value.includes('try')) {
    tryRunOpen.value = ['try']
  }
})
</script>

<style scoped lang="scss">
.csv-perf-hint {
  margin: 10px 0 14px;
}

.csv-perf-hint__alert :deep(.el-alert__content) {
  width: 100%;
}

.csv-perf-hint__body {
  font-size: 12px;
  line-height: 1.65;
  color: var(--el-text-color-regular);

  p {
    margin: 0 0 6px;
  }
}

.csv-perf-hint__muted {
  color: var(--el-text-color-secondary);
}

.csv-perf-hint__link {
  color: var(--el-color-primary);
  margin-right: 10px;
  text-decoration: none;

  &:hover {
    text-decoration: underline;
  }
}

.csv-try-run {
  margin-top: 8px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  overflow: hidden;
}

.csv-try-run__title {
  font-weight: 500;
  font-size: 13px;
}

.csv-try-run__hint {
  margin: 0 0 10px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.6;
}

.csv-try-run__preview {
  margin: 0;
  max-height: 120px;
  overflow: auto;
  padding: 8px 10px;
  background: var(--el-fill-color-light);
  border-radius: 6px;
  font-size: 12px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  width: 100%;
}
</style>
