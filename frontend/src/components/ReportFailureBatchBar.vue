<template>
  <div v-if="visible" class="report-batch-bar">
    <KnowledgeRefSelector
      v-model="knowledgeRefs"
      label=""
      hint="可选：引用历史 Bug / 测试计划辅助失败分析"
      :show-estimate="false"
      :show-retrieve-preview="false"
      folder-placeholder="资料库文件夹（可选）"
    />
    <div v-if="supportsVision" class="vision-toggle-row">
      <el-switch
        v-model="useVision"
        active-text="截图识图"
        inactive-text="纯文本"
        size="small"
      />
      <span class="vision-hint">{{ useVision ? '批量识图费用较高' : '批量纯文本（推荐）' }}</span>
    </div>
    <el-button type="warning" :loading="loading" @click="run">
      批量 AI 分析失败
    </el-button>
    <el-collapse v-if="batchResults.length" v-model="resultCollapse" class="batch-result-panel">
      <el-collapse-item name="results" :title="`分析结果（${successCount}/${batchResults.length} 成功）`">
        <div v-if="canArchiveToKnowledge" class="archive-bar">
          <el-select
            v-model="archiveFolderId"
            clearable
            filterable
            placeholder="归档到文件夹（可选）"
            style="width: 220px;"
            size="small"
          >
            <el-option v-for="f in archiveFolders" :key="f.id" :label="folderLabel(f)" :value="f.id" />
          </el-select>
          <el-button size="small" type="success" :loading="archiving" @click="archiveResults">
            归档分析摘要到资料库
          </el-button>
        </div>
        <el-table :data="batchResults" size="small" stripe border max-height="320">
          <el-table-column prop="case_name" label="用例" min-width="140" show-overflow-tooltip>
            <template #default="{ row }">
              {{ row.case_name || `${row.target_type}#${row.target_id}` }}
            </template>
          </el-table-column>
          <el-table-column label="状态" width="72" align="center">
            <template #default="{ row }">
              <el-tag :type="row.ok ? 'success' : 'danger'" size="small">{{ row.ok ? '成功' : '失败' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="root_cause" label="根因摘要" min-width="200" show-overflow-tooltip>
            <template #default="{ row }">
              {{ row.root_cause || row.error || '—' }}
            </template>
          </el-table-column>
        </el-table>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { aiAnalyzeApi } from '@/api/modules/ai.js'
import { knowledgeApi } from '@/api/modules/knowledge.js'
import { useCommunityEdition } from '@/composables/useCommunityEdition.js'
import KnowledgeRefSelector from '@/modules/knowledge/components/KnowledgeRefSelector.vue'
import { UserStore } from '@/stores/module/UserStore.js'

const props = defineProps({
  visible: { type: Boolean, default: true },
  projectId: { type: [Number, String], required: true },
  reportType: { type: String, required: true },
  recordId: { type: [Number, String], required: true },
  limit: { type: Number, default: 5 },
  recordTitle: { type: String, default: '' }
})

const loading = ref(false)
const archiving = ref(false)
const useVision = ref(false)
const knowledgeRefs = ref({ folder_ids: [], document_ids: [] })
const batchResults = ref([])
const resultCollapse = ref(['results'])
const archiveFolders = ref([])
const archiveFolderId = ref(null)

const { isCommunityEdition, loadCommunityEdition } = useCommunityEdition()
const editionReady = ref(false)
const canArchive = computed(() => {
  const u = UserStore()
  return u.hasPermission('knowledge:edit') || u.hasPermission('knowledge:execute')
})
const canArchiveToKnowledge = computed(
  () => editionReady.value && canArchive.value
)
const successCount = computed(() => batchResults.value.filter(r => r.ok).length)
const supportsVision = computed(() => {
  const t = String(props.reportType || '')
  return t.startsWith('ui_') || t.startsWith('app_')
})

function folderLabel(f) {
  return f.iteration_label ? `${f.name} (${f.iteration_label})` : f.name
}

function formatArchiveMarkdown() {
  const lines = [
    `# 失败分析摘要`,
    ``,
    `- 报告类型：${props.reportType}`,
    `- 记录 ID：${props.recordId}`,
    props.recordTitle ? `- 名称：${props.recordTitle}` : null,
    `- 分析时间：${new Date().toLocaleString()}`,
    `- 成功：${successCount.value}/${batchResults.value.length}`,
    ``,
    `## 明细`,
    ``
  ].filter(Boolean)
  for (const row of batchResults.value) {
    const name = row.case_name || `${row.target_type}#${row.target_id}`
    lines.push(`### ${name}`)
    lines.push(`- 状态：${row.ok ? '成功' : '失败'}`)
    lines.push(`- 根因：${row.root_cause || row.error || '—'}`)
    if (row.suggestion) lines.push(`- 建议：${row.suggestion}`)
    lines.push('')
  }
  return lines.join('\n')
}

async function loadArchiveFolders() {
  if (!props.projectId || !canArchiveToKnowledge.value) return
  try {
    const res = await knowledgeApi.listFolders(props.projectId)
    archiveFolders.value = res.data?.items || []
  } catch {
    archiveFolders.value = []
  }
}

async function archiveResults() {
  if (!props.projectId || !batchResults.value.length || !canArchiveToKnowledge.value) return
  archiving.value = true
  try {
    const title = props.recordTitle
      ? `失败分析-${props.recordTitle}`.slice(0, 200)
      : `失败分析-${props.reportType}#${props.recordId}`
    const res = await knowledgeApi.archiveFromText(
      {
        title,
        content: formatArchiveMarkdown(),
        folder_id: archiveFolderId.value || undefined,
        doc_type: 'summary',
        source_key: `failure_batch:${props.reportType}:${props.recordId}`,
        replace_if_exists: true
      },
      props.projectId
    )
    ElMessage.success(res.message || '已归档到资料库')
  } catch (e) {
    ElMessage.error(e?.message || '归档失败')
  } finally {
    archiving.value = false
  }
}

async function run() {
  if (!props.projectId || !props.recordId) return
  loading.value = true
  batchResults.value = []
  try {
    const folderIds = (knowledgeRefs.value.folder_ids || []).filter(Boolean)
    const docIds = (knowledgeRefs.value.document_ids || []).filter(Boolean)
    const res = await aiAnalyzeApi.analyzeFailureBatch(
      {
        report_type: props.reportType,
        record_id: Number(props.recordId),
        limit: props.limit,
        use_vision: useVision.value,
        ...(folderIds.length ? { knowledge_folder_ids: folderIds } : {}),
        ...(docIds.length ? { knowledge_document_ids: docIds } : {})
      },
      props.projectId
    )
    const body = res.data
    if (body?.code === 200) {
      batchResults.value = body.data?.results || []
      resultCollapse.value = ['results']
      ElMessage.success(body.message || '批量分析完成')
    }
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '批量分析失败')
  } finally {
    loading.value = false
  }
}

watch(
  () => knowledgeRefs.value.folder_ids,
  (ids) => {
    if (ids?.length === 1) archiveFolderId.value = ids[0]
  },
  { deep: true }
)

onMounted(async () => {
  await loadCommunityEdition()
  editionReady.value = true
  await loadArchiveFolders()
})

defineExpose({ run })
</script>

<style scoped>
.report-batch-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 8px;
  max-width: 720px;
}
.report-batch-bar :deep(.el-form-item) {
  margin-bottom: 0;
  flex: 1;
  min-width: 260px;
}
.batch-result-panel {
  width: 100%;
  flex-basis: 100%;
}
.archive-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-bottom: 10px;
}
.vision-toggle-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.vision-hint {
  font-size: 12px;
  color: #909399;
}
</style>
