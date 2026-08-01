<template>
  <div>
    <el-card shadow="never" class="mapping-card" v-loading="mappingLoading">
      <template #header>
        <div class="mapping-head">
          <b>默认模板映射（按报告类型）</b>
          <span class="mapping-sub">报告向导未手动选模板时，按类型使用下表配置；未配置则沿用「全局默认」或内置模板</span>
        </div>
      </template>
      <el-table :data="mappingItems" size="small" stripe>
        <el-table-column prop="label" label="报告类型" width="128" />
        <el-table-column label="默认模板" min-width="240">
          <template #default="{ row }">
            <el-select
              v-model="mappingSelection[row.report_kind]"
              style="width: 100%;"
              :disabled="!canExecute"
              @change="onMappingChange(row.report_kind)"
            >
              <el-option :value="UNSET_VALUE" label="未单独配置（跟随全局默认 → 内置）" />
              <el-option :value="BUILTIN_VALUE" label="使用内置通用模板" />
              <el-option
                v-for="c in row.candidates"
                :key="c.id"
                :value="c.id"
                :label="`${c.title} (${c.file_name})`"
              />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="当前生效" min-width="180">
          <template #default="{ row }">
            <span>{{ row.effective?.template_name || '-' }}</span>
            <el-tag size="small" class="src-tag">{{ effectiveSourceLabel(row.effective?.effective_source) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="占位符" width="108" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.effective?.empty" type="danger" size="small">无</el-tag>
            <el-tag v-else type="success" size="small">{{ row.effective?.known_count ?? 0 }} 个</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="缺陷占位" width="96" align="center">
          <template #default="{ row }">
            <template v-if="row.needs_bug_placeholders">
              <el-tag v-if="row.effective?.covers_bug_data" type="success" size="small">齐全</el-tag>
              <el-tag v-else type="warning" size="small">缺失</el-tag>
            </template>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="downloadBuiltinForKind(row.report_kind)">下载内置</el-button>
            <el-button link type="primary" @click="validateMappingRow(row)">校验</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <div class="toolbar">
      <el-dropdown @command="downloadBuiltin">
        <el-button type="primary">
          下载内置通用模板
          <el-icon class="el-icon--right"><arrow-down /></el-icon>
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item
              v-for="item in builtinTemplates"
              :key="item.kind"
              :command="item"
            >
              {{ item.label }}
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <el-button @click="reloadAll">刷新</el-button>
    </div>

    <el-alert type="info" show-icon :closable="false" class="tip">
      各公司可下载通用模板作起点，在 Word 中用 <code v-pre>{{ 变量名 }}</code> 标注需自动填充的位置。
      缺陷章节推荐 <code v-pre>{{ bug_analysis_text }}</code> 或表格循环 <code v-pre>{{ bug_stats_rows }}</code>。
      <router-link to="/ai-knowledge/variables" class="var-link">模板变量说明</router-link>
    </el-alert>

    <el-table :data="list" v-loading="loading" stripe>
      <el-table-column prop="title" label="模板名称" min-width="160" />
      <el-table-column prop="doc_type_label" label="类型" width="120" />
      <el-table-column prop="file_name" label="文件名" min-width="180" show-overflow-tooltip />
      <el-table-column label="占位符" width="120" align="center">
        <template #default="{ row }">
          <el-tag v-if="validateInfo(row).empty" type="danger" size="small">无占位符</el-tag>
          <el-tag v-else-if="validateInfo(row).knownCount > 0" type="success" size="small">
            {{ validateInfo(row).knownCount }} 个已知
          </el-tag>
          <el-tag v-else-if="validateInfo(row).total > 0" type="warning" size="small">
            {{ validateInfo(row).total }} 个未识别
          </el-tag>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column label="全局默认" width="88" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.is_default_template" type="success" size="small">是</el-tag>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="{ row }">
          <el-button v-if="canExecute" link type="primary" @click="validate(row)">校验占位符</el-button>
          <el-button v-if="canExecute" link type="primary" @click="setDefault(row)">设为全局默认</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="validateDialog.visible" :title="validateDialog.title" width="520px">
      <template v-if="validateDialog.data">
        <el-alert
          v-if="validateDialog.data.empty"
          type="error"
          :closable="false"
          show-icon
          title="未发现任何 {{ 变量 }} 占位符"
          description="此模板无法自动填充。请下载内置通用模板对照，或在 Word 中插入 {{ bug_analysis_text }}、{{ overview }} 等变量。"
          style="margin-bottom: 12px;"
        />
        <p v-if="validateDialog.data.known?.length">
          <b>已识别变量（{{ validateDialog.data.known.length }}）：</b>
          {{ validateDialog.data.known.join('、') }}
        </p>
        <p v-if="validateDialog.data.unknown?.length" class="unknown-line">
          <b>未在注册表中的变量（{{ validateDialog.data.unknown.length }}）：</b>
          {{ validateDialog.data.unknown.join('、') }}
        </p>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { ArrowDown } from '@element-plus/icons-vue'
import { knowledgeApi } from '@/api/modules/knowledge.js'
import { ProjectStore } from '@/stores/module/ProjectStore.js'
import { useKnowledgePermissions } from '@/modules/knowledge/composables/useKnowledgePermissions.js'

const BUILTIN_VALUE = '__builtin__'
const UNSET_VALUE = '__unset__'

const projectId = computed(() => ProjectStore().projectInfo?.id)
const { canEdit: canExecute } = useKnowledgePermissions()

const loading = ref(false)
const mappingLoading = ref(false)
const list = ref([])
const builtinTemplates = ref([])
const mappingItems = ref([])
const mappingSelection = ref({})
const validateMap = ref({})
const validateDialog = ref({ visible: false, title: '', data: null })

const EFFECTIVE_SOURCE_LABEL = {
  builtin: '内置',
  project_kind_default: '类型默认',
  project_kind_builtin: '内置(已配置)',
  legacy_global_default: '全局默认',
  uploaded: '上传'
}

function effectiveSourceLabel(src) {
  return EFFECTIVE_SOURCE_LABEL[src] || src || '-'
}

function schemaOf(row) {
  return validateMap.value[row.id] || row.template_schema || null
}

function validateInfo(row) {
  const s = schemaOf(row)
  if (!s) return { total: 0, knownCount: 0, empty: false }
  const known = s.known || []
  const unknown = s.unknown || []
  const placeholders = s.placeholders || []
  const total = placeholders.length || known.length + unknown.length
  return { total, knownCount: known.length, empty: total === 0 }
}

function syncMappingSelection(items) {
  const next = {}
  for (const row of items || []) {
    if (row.configured_mode === 'unset') {
      next[row.report_kind] = UNSET_VALUE
    } else if (row.configured_mode === 'builtin') {
      next[row.report_kind] = BUILTIN_VALUE
    } else if (row.configured_mode === 'uploaded' && row.configured_template_doc_id) {
      next[row.report_kind] = row.configured_template_doc_id
    } else {
      next[row.report_kind] = UNSET_VALUE
    }
  }
  mappingSelection.value = next
}

async function loadMapping() {
  if (!projectId.value) return
  mappingLoading.value = true
  try {
    const res = await knowledgeApi.getTemplateDefaults(projectId.value)
    mappingItems.value = res.data?.items || []
    syncMappingSelection(mappingItems.value)
  } catch (e) {
    ElMessage.error(e?.message || '加载默认映射失败')
  } finally {
    mappingLoading.value = false
  }
}

async function loadList() {
  if (!projectId.value) return
  loading.value = true
  try {
    const [reportRes, planRes] = await Promise.all([
      knowledgeApi.listDocuments(projectId.value, { doc_type: 'report_template', size: 100 }),
      knowledgeApi.listDocuments(projectId.value, { doc_type: 'plan_template', size: 100 })
    ])
    list.value = [...(reportRes.data?.items || []), ...(planRes.data?.items || [])]
  } catch (e) {
    ElMessage.error(e?.message || '加载失败')
  } finally {
    loading.value = false
  }
}

async function reloadAll() {
  await Promise.all([loadMapping(), loadList()])
}

async function loadBuiltinTemplates() {
  try {
    const res = await knowledgeApi.listBuiltinTemplates()
    builtinTemplates.value = res.data?.items || []
  } catch {
    builtinTemplates.value = []
  }
}

async function onMappingChange(reportKind) {
  if (!canExecute.value || !projectId.value) return
  const val = mappingSelection.value[reportKind]
  const payload = {
    [reportKind]: val === BUILTIN_VALUE ? null : val === UNSET_VALUE ? 'unset' : val
  }
  mappingLoading.value = true
  try {
    const res = await knowledgeApi.updateTemplateDefaults(payload, projectId.value)
    mappingItems.value = res.data?.items || []
    syncMappingSelection(mappingItems.value)
    ElMessage.success('已更新默认模板')
  } catch (e) {
    ElMessage.error(e?.message || '保存失败')
    await loadMapping()
  } finally {
    mappingLoading.value = false
  }
}

async function validate(row) {
  try {
    const res = await knowledgeApi.validateTemplate(row.id, projectId.value)
    openValidateDialog(row.title, res.data)
  } catch (e) {
    ElMessage.error(e?.message || '校验失败')
  }
}

function isUploadedTemplateId(val) {
  return typeof val === 'number' || (typeof val === 'string' && /^\d+$/.test(val))
}

async function validateMappingRow(row) {
  const sel = mappingSelection.value[row.report_kind]
  const params = { report_kind: row.report_kind }
  let title = `${row.label} · 当前生效`
  if (isUploadedTemplateId(sel)) {
    params.template_doc_id = Number(sel)
    const hit = (row.candidates || []).find((c) => c.id === Number(sel))
    title = hit?.title || row.label
  }
  try {
    const res = await knowledgeApi.inspectReportTemplate(projectId.value, params)
    openValidateDialog(title, res.data || {})
  } catch (e) {
    ElMessage.error(e?.message || '校验失败')
  }
}

function openValidateDialog(title, data) {
  const known = data?.known || []
  const unknown = data?.unknown || []
  const empty = data?.empty ?? !(data?.placeholders?.length || known.length || unknown.length)
  validateDialog.value = {
    visible: true,
    title: `占位符校验 · ${title}`,
    data: { ...data, empty }
  }
  if (empty) {
    ElMessage.warning('未发现占位符')
  } else if (unknown.length) {
    ElMessage.warning(`发现 ${unknown.length} 个未识别变量`)
  } else {
    ElMessage.success(`识别 ${known.length} 个可用变量`)
  }
}

async function setDefault(row) {
  try {
    await knowledgeApi.setDefaultTemplate(row.id, projectId.value)
    ElMessage.success('已设为全局默认（未单独配置的报告类型将沿用）')
    await reloadAll()
  } catch (e) {
    ElMessage.error(e?.message || '操作失败')
  }
}

function triggerDownload(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

async function downloadBuiltin(item) {
  const kind = item?.kind || 'iteration_report'
  const filename = item?.filename || '通用迭代自动化测试报告模板.docx'
  try {
    const blob = await knowledgeApi.downloadDefaultTemplate(kind)
    triggerDownload(blob, filename)
  } catch (e) {
    ElMessage.error(e?.message || '下载失败')
  }
}

function downloadBuiltinForKind(reportKind) {
  const item = builtinTemplates.value.find((t) => t.kind === reportKind)
  downloadBuiltin(item || { kind: reportKind })
}

watch(projectId, async () => {
  await reloadAll()
})

onMounted(async () => {
  await loadBuiltinTemplates()
  await reloadAll()
})
</script>

<style scoped>
.mapping-card {
  margin-bottom: 16px;
}
.mapping-head {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.mapping-sub {
  font-size: 12px;
  font-weight: normal;
  color: var(--el-text-color-secondary);
}
.src-tag {
  margin-left: 6px;
}
.toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
.tip {
  margin-bottom: 12px;
}
.var-link {
  margin-left: 8px;
  color: var(--el-color-primary);
  text-decoration: none;
}
.unknown-line {
  margin-top: 8px;
  color: var(--el-color-warning);
}
</style>
