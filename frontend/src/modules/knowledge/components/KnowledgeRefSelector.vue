<template>
  <div v-if="editionReady && canRefKnowledge" class="knowledge-ref-selector">
    <el-form-item :label="label">
      <el-select
        v-model="selectedFolderIds"
        multiple
        collapse-tags
        collapse-tags-tooltip
        :placeholder="folderPlaceholder"
        style="width: 100%;"
        :loading="loadingFolders"
        :disabled="disabled"
        @change="onFoldersChange"
      >
        <el-option v-for="f in folders" :key="f.id" :label="folderLabel(f)" :value="f.id" />
      </el-select>

      <div v-if="showDocuments && selectedFolderIds.length" class="doc-panel">
        <div class="doc-panel-head">
          <span>勾选文档（可选，不勾选则使用该文件夹下全部文档）</span>
          <el-button v-if="selectedDocIds.length" link type="primary" @click="clearDocs">清空勾选</el-button>
        </div>
        <div v-if="loadingDocs" class="doc-panel-hint">正在加载文档列表…</div>
        <div v-else-if="docsLoadError" class="doc-panel-error">{{ docsLoadError }}</div>
        <div v-else-if="!folderDocs.length" class="doc-panel-hint">该文件夹下暂无文档</div>
        <template v-else>
        <el-checkbox-group
          v-if="documentMode !== 'single'"
          v-model="selectedDocIds"
          @change="emitChange"
        >
          <el-checkbox v-for="d in folderDocs" :key="d.id" :value="d.id" class="doc-item">
            {{ d.title }}
            <span class="doc-meta">{{ d.doc_type_label || d.doc_type }} · {{ formatChars(d.char_count) }}</span>
            <el-button v-if="allowPreview" link type="primary" @click.stop="openPreview(d)">预览</el-button>
          </el-checkbox>
        </el-checkbox-group>
        <el-radio-group
          v-else
          v-model="singleDocId"
          @change="onSingleDocChange"
        >
          <el-radio v-for="d in folderDocs" :key="d.id" :value="d.id" class="doc-item">
            {{ d.title }}
            <span class="doc-meta">{{ formatChars(d.char_count) }}</span>
            <el-button v-if="allowPreview" link type="primary" @click.stop="openPreview(d)">预览</el-button>
          </el-radio>
        </el-radio-group>
        </template>
      </div>

      <div v-if="showEstimate && estimateText" class="estimate-line">
        <el-icon><InfoFilled /></el-icon>
        {{ estimateText }}
      </div>
      <KnowledgeReferenceCards
        v-if="showRefCards && (estimate?.refs?.length || estimate?.bug_hints?.has_hints)"
        :refs="estimate?.refs || []"
        :bug-hints="estimate?.bug_hints"
        :strategy-label="estimate?.strategy_label"
      />
      <div v-if="hint" class="hint">{{ hint }}</div>

      <div v-if="showRetrievePreview" class="retrieve-panel">
        <div class="retrieve-row">
          <el-input
            v-model="retrieveQuery"
            size="small"
            clearable
            placeholder="输入关键词预览检索命中（可选）"
            @keyup.enter="runRetrievePreview"
          />
          <el-button size="small" type="primary" plain :loading="retrieveLoading" @click="runRetrievePreview">
            检索预览
          </el-button>
        </div>
        <div v-if="retrievePreview?.chunks?.length" class="retrieve-hits">
          <div v-for="(hit, idx) in retrievePreview.chunks.slice(0, 5)" :key="idx" class="retrieve-hit">
            <span class="hit-title">《{{ hit.title }}》</span>
            <span v-if="hit.score != null" class="hit-score">{{ hit.score }}</span>
            <span class="hit-text">{{ hit.text }}</span>
          </div>
          <div v-if="retrievePreview.strategy" class="retrieve-meta">
            {{ retrieveStrategyLabel(retrievePreview.strategy) }} · {{ retrievePreview.hit_count || 0 }} 条
          </div>
        </div>
      </div>
    </el-form-item>

    <el-drawer v-model="previewVisible" :title="previewTitle" size="480px" destroy-on-close>
      <div v-loading="previewLoading" class="preview-body">
        <el-empty v-if="!previewLoading && !previewText" description="暂无预览内容" />
        <pre v-else class="preview-pre">{{ previewText }}</pre>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { InfoFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { knowledgeApi } from '@/api/modules/knowledge.js'
import { useCommunityEdition } from '@/composables/useCommunityEdition.js'
import { ProjectStore } from '@/stores/module/ProjectStore.js'
import { UserStore } from '@/stores/module/UserStore.js'
import KnowledgeReferenceCards from '@/modules/knowledge/components/KnowledgeReferenceCards.vue'

const canRefKnowledge = computed(() => UserStore().hasPermission('knowledge:view'))

const props = defineProps({
  modelValue: {
    type: Object,
    default: () => ({ folder_ids: [], document_ids: [] })
  },
  label: { type: String, default: '引用资料库' },
  hint: {
    type: String,
    default: '可选：引用历史 Bug、测试计划等，帮助 AI 补充上下文'
  },
  /** folders | documents | both */
  mode: { type: String, default: 'both' },
  /** single | multiple */
  documentMode: { type: String, default: 'multiple' },
  showEstimate: { type: Boolean, default: true },
  showRefCards: { type: Boolean, default: true },
  showRetrievePreview: { type: Boolean, default: true },
  allowPreview: { type: Boolean, default: true },
  disabled: { type: Boolean, default: false },
  folderPlaceholder: { type: String, default: '选择迭代文件夹（可选）' }
})

const emit = defineEmits(['update:modelValue'])

const { isCommunityEdition, loadCommunityEdition } = useCommunityEdition()
const editionReady = ref(false)
const loadingFolders = ref(false)
const folders = ref([])
const folderDocs = ref([])
const loadingDocs = ref(false)
const docsLoadError = ref('')
const selectedFolderIds = ref([...(props.modelValue?.folder_ids || [])])
const selectedDocIds = ref([...(props.modelValue?.document_ids || [])])
const singleDocId = ref(props.modelValue?.document_ids?.[0] ?? null)
const estimate = ref(null)
const estimateTimer = ref(null)
const previewVisible = ref(false)
const previewLoading = ref(false)
const previewTitle = ref('')
const previewText = ref('')
const retrieveQuery = ref('')
const retrieveLoading = ref(false)
const retrievePreview = ref(null)

const showDocuments = computed(() => props.mode === 'both' || props.mode === 'documents')

const estimateText = computed(() => {
  const e = estimate.value
  if (!e || (!e.doc_count && !selectedFolderIds.value.length && !selectedDocIds.value.length)) return ''
  const chars = e.raw_total_chars || 0
  const label = e.strategy_label || ''
  return `约 ${formatChars(chars)} 字 · ${e.doc_count || 0} 篇文档 · ${label}`
})

function folderLabel(f) {
  const tag = f.iteration_label ? ` (${f.iteration_label})` : ''
  return `${f.name}${tag} · ${f.doc_count || 0} 文档`
}

function formatChars(n) {
  const v = Number(n) || 0
  if (v >= 10000) return `${(v / 10000).toFixed(1)}万`
  return v.toLocaleString()
}

function emitChange() {
  const docIds = props.documentMode === 'single'
    ? (singleDocId.value ? [singleDocId.value] : [])
    : [...selectedDocIds.value]
  emit('update:modelValue', {
    folder_ids: [...selectedFolderIds.value],
    document_ids: docIds
  })
  scheduleEstimate()
}

function onSingleDocChange() {
  selectedDocIds.value = singleDocId.value ? [singleDocId.value] : []
  emitChange()
}

function clearDocs() {
  selectedDocIds.value = []
  singleDocId.value = null
  emitChange()
}

async function loadFolderDocs() {
  const pid = ProjectStore().projectInfo?.id
  if (!pid || !selectedFolderIds.value.length || !showDocuments.value) {
    folderDocs.value = []
    docsLoadError.value = ''
    return
  }
  loadingDocs.value = true
  docsLoadError.value = ''
  const all = []
  try {
    for (const fid of selectedFolderIds.value) {
      let page = 1
      let folderLoaded = 0
      while (page <= 20) {
        const res = await knowledgeApi.listDocuments(pid, { folder_id: fid, page, size: 100 })
        const items = res.data?.items || []
        all.push(...items)
        folderLoaded += items.length
        const total = Number(res.data?.total) || items.length
        if (items.length < 100 || folderLoaded >= total) break
        page += 1
      }
    }
    folderDocs.value = all
    const valid = new Set(all.map((d) => d.id))
    selectedDocIds.value = selectedDocIds.value.filter((id) => valid.has(id))
    if (singleDocId.value && !valid.has(singleDocId.value)) {
      singleDocId.value = null
    }
  } catch (e) {
    folderDocs.value = []
    docsLoadError.value = e?.message || '加载文档列表失败'
    ElMessage.error(docsLoadError.value)
  } finally {
    loadingDocs.value = false
  }
}

async function onFoldersChange() {
  await loadFolderDocs()
  emitChange()
}

function scheduleEstimate() {
  if (!props.showEstimate) return
  if (estimateTimer.value) clearTimeout(estimateTimer.value)
  estimateTimer.value = setTimeout(refreshEstimate, 400)
  retrievePreview.value = null
}

function retrieveStrategyLabel(s) {
  return { rag: 'RAG', fulltext: '全文', none: '无' }[s] || s
}

async function runRetrievePreview() {
  const pid = ProjectStore().projectInfo?.id
  const q = (retrieveQuery.value || '').trim()
  const folderIds = selectedFolderIds.value.filter(Boolean)
  const docIds = props.documentMode === 'single'
    ? (singleDocId.value ? [singleDocId.value] : [])
    : selectedDocIds.value.filter(Boolean)
  if (!pid) return
  if (!q) {
    ElMessage.warning('请输入检索关键词')
    return
  }
  if (!folderIds.length && !docIds.length) {
    ElMessage.warning('请先选择文件夹或文档')
    return
  }
  retrieveLoading.value = true
  try {
    const res = await knowledgeApi.retrieveKnowledge(
      {
        query: q,
        top_k: 8,
        ...(folderIds.length ? { folder_ids: folderIds } : {}),
        ...(docIds.length ? { document_ids: docIds } : {})
      },
      pid
    )
    retrievePreview.value = res.data || null
  } catch (e) {
    retrievePreview.value = null
    ElMessage.error(e?.message || '检索预览失败')
  } finally {
    retrieveLoading.value = false
  }
}

async function refreshEstimate() {
  const pid = ProjectStore().projectInfo?.id
  const folderIds = selectedFolderIds.value
  const docIds = props.documentMode === 'single'
    ? (singleDocId.value ? [singleDocId.value] : [])
    : selectedDocIds.value
  if (!pid || (!folderIds.length && !docIds.length)) {
    estimate.value = null
    return
  }
  try {
    const res = await knowledgeApi.estimateKnowledgeRefs(
      { folder_ids: folderIds.length ? folderIds : undefined, document_ids: docIds.length ? docIds : undefined },
      pid
    )
    estimate.value = res.data || null
  } catch {
    estimate.value = null
  }
}

async function openPreview(doc) {
  const pid = ProjectStore().projectInfo?.id
  if (!pid || !doc?.id) return
  previewTitle.value = doc.title || '文档预览'
  previewVisible.value = true
  previewLoading.value = true
  previewText.value = ''
  try {
    const res = await knowledgeApi.previewDocument(doc.id, pid)
    const data = res.data || {}
    previewText.value = data.preview_text || data.text || ''
  } catch (e) {
    previewText.value = e?.message || '预览失败'
  } finally {
    previewLoading.value = false
  }
}

watch(
  () => props.modelValue,
  (v) => {
    selectedFolderIds.value = [...(v?.folder_ids || [])]
    selectedDocIds.value = [...(v?.document_ids || [])]
    singleDocId.value = v?.document_ids?.[0] ?? null
  },
  { deep: true }
)

async function loadFolders() {
  const pid = ProjectStore().projectInfo?.id
  if (!pid) return
  loadingFolders.value = true
  try {
    const res = await knowledgeApi.listFolders(pid)
    folders.value = res.data?.items || []
  } finally {
    loadingFolders.value = false
  }
}

onMounted(async () => {
  await loadCommunityEdition()
  editionReady.value = true
  await loadFolders()
  if (selectedFolderIds.value.length) {
    await loadFolderDocs()
  }
  scheduleEstimate()
})
</script>

<style scoped>
.hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}
.doc-panel {
  margin-top: 8px;
  padding: 8px 10px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  max-height: 280px;
  overflow-y: auto;
  background: var(--el-fill-color-blank);
}
.doc-panel-hint,
.doc-panel-error {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  padding: 6px 0;
}
.doc-panel-error {
  color: var(--el-color-danger);
}
.doc-panel-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 6px;
}
.doc-item {
  display: flex;
  align-items: center;
  width: 100%;
  margin-right: 0;
  font-size: 13px;
}
.doc-meta {
  margin-left: 6px;
  font-size: 11px;
  color: var(--el-text-color-secondary);
}
.estimate-line {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-color-primary);
}
.preview-body {
  min-height: 120px;
}
.preview-pre {
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 13px;
  line-height: 1.6;
  margin: 0;
}
.retrieve-panel {
  margin-top: 8px;
}
.retrieve-row {
  display: flex;
  gap: 8px;
  align-items: center;
}
.retrieve-row .el-input {
  flex: 1;
}
.retrieve-hits {
  margin-top: 8px;
  padding: 8px 10px;
  border: 1px dashed var(--el-border-color);
  border-radius: 6px;
  max-height: 160px;
  overflow-y: auto;
}
.retrieve-hit {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  font-size: 12px;
  margin-bottom: 6px;
  line-height: 1.5;
}
.hit-title {
  color: var(--el-color-primary);
  font-weight: 500;
}
.hit-score {
  color: var(--el-text-color-secondary);
}
.hit-text {
  flex: 1 1 100%;
  color: var(--el-text-color-regular);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.retrieve-meta {
  font-size: 11px;
  color: var(--el-text-color-secondary);
}
</style>
