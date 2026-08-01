<template>
  <div class="knowledge-qa">
    <div class="qa-layout">
      <aside class="history-panel">
        <div class="history-head">
          <b>问答历史</b>
          <div class="history-actions">
            <el-checkbox
              v-if="historyItems.length"
              v-model="selectAll"
              :indeterminate="selectIndeterminate"
              size="small"
              @change="toggleSelectAll"
              @click.stop
            >
              全选
            </el-checkbox>
            <el-button
              v-if="canEdit"
              link
              type="danger"
              size="small"
              :disabled="!selectedRecordIds.length"
              @click="batchRemoveRecords"
            >
              批量删除
            </el-button>
            <el-button link type="primary" size="small" :loading="loadingHistory" @click="loadHistory">刷新</el-button>
          </div>
        </div>
        <div v-if="loadingHistory && !historyItems.length" class="history-empty">加载中…</div>
        <div v-else-if="!historyItems.length" class="history-empty">暂无记录，提问后将自动保存</div>
        <ul v-else class="history-list">
          <li
            v-for="item in historyItems"
            :key="item.id"
            class="history-item"
            :class="{ active: activeRecordId === item.id, selected: selectedRecordIds.includes(item.id) }"
            @click="restoreRecord(item.id)"
          >
            <el-checkbox
              class="history-check"
              :model-value="selectedRecordIds.includes(item.id)"
              @change="val => toggleRecordSelect(item.id, val)"
              @click.stop
            />
            <div class="history-item-body">
            <div class="history-item-top">
              <el-tag size="small" :type="item.mode === 'smart' ? 'primary' : 'info'">
                {{ item.mode === 'smart' ? '智能' : '检索' }}
              </el-tag>
              <span class="history-time">{{ formatTime(item.create_time) }}</span>
            </div>
            <div class="history-query">{{ item.query }}</div>
            <div v-if="item.answer_preview" class="history-preview">{{ item.answer_preview }}</div>
            <div class="history-meta">
              {{ item.hit_count || 0 }} 条 · {{ strategyLabel(item.answer_path || item.strategy) }}
            </div>
            <el-button
              v-if="canEdit"
              class="history-del"
              link
              type="danger"
              size="small"
              @click.stop="removeRecord(item)"
            >
              删除
            </el-button>
            </div>
          </li>
        </ul>
        <div v-if="historyTotal > historyItems.length" class="history-more">
          共 {{ historyTotal }} 条，仅显示最近 {{ historyItems.length }} 条
        </div>
      </aside>

      <div class="qa-main">
        <el-card shadow="never">
          <el-form :model="form" label-width="88px" @submit.prevent>
            <el-form-item label="问答模式">
              <el-radio-group v-model="form.mode">
                <el-radio-button value="retrieve">检索模式</el-radio-button>
                <el-radio-button value="smart" :disabled="!canRunKnowledge">智能模式</el-radio-button>
              </el-radio-group>
              <div class="mode-hint">
                <span v-if="form.mode === 'retrieve'">直接返回 Top-K 分块，不消耗 LLM Token</span>
                <span v-else-if="!canRunKnowledge">智能模式需「资料库-执行」权限；检索模式可直接使用</span>
                <span v-else>先检索资料片段，再调用 LLM 生成回答</span>
              </div>
            </el-form-item>
            <el-form-item label="问题" required>
              <el-input
                v-model="form.query"
                type="textarea"
                :rows="2"
                maxlength="500"
                show-word-limit
                placeholder="例如：登录模块有哪些未关闭缺陷？本轮测试范围是什么？"
                @keyup.enter.ctrl="ask"
              />
            </el-form-item>
            <KnowledgeRefSelector
              v-model="form.scope"
              label="限定范围"
              hint="先选迭代文件夹，再勾选 1～N 份文档可显著减少干扰、提高准确度；不勾选文档则检索整个文件夹；文件夹也不选则检索项目内全部已索引资料"
              :show-estimate="false"
              :show-ref-cards="false"
              :show-retrieve-preview="false"
              folder-placeholder="选择迭代文件夹（推荐）"
            />
            <div class="scope-tip">
              表格统计题（如「某人 bug 有多少」）请在上方限定 <b>1 份</b> Excel/CSV，并确保已「重新解析」为 v2；长文档章节题建议限定 1～3 份相关文件。
            </div>
            <div class="scope-tip">
              资料越多，Top-K 越容易漏项；泛化总结类问题可将返回条数调到 20～30。
            </div>
            <el-form-item label="返回条数">
              <el-input-number v-model="form.top_k" :min="1" :max="30" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="asking" @click="ask">
                {{ form.mode === 'smart' ? '提问' : '检索' }}
              </el-button>
              <el-button @click="resetForm">重置</el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <el-card v-if="result || asking" shadow="never" class="result-card">
          <template #header>
            <div class="result-head">
              <b>{{ form.mode === 'smart' ? '问答结果' : '检索结果' }}</b>
              <el-tag v-if="result?.answer_path || result?.strategy" size="small" :type="strategyTag(result.answer_path || result.strategy)">
                {{ strategyLabel(result.answer_path || result.strategy) }}
              </el-tag>
              <span v-if="result" class="result-meta">
                {{ result.hit_count || 0 }} 条引用 · {{ result.doc_count || 0 }} 篇文档
              </span>
            </div>
          </template>

          <div v-if="asking && form.mode === 'smart'" class="waiting-box">
            <el-icon class="is-loading"><Loading /></el-icon>
            <span>正在检索资料并生成回答，请稍候…</span>
          </div>

          <el-alert
            v-if="form.mode === 'retrieve' && result && !result.chunks?.length && !result.context_text && !result.answer"
            type="info"
            :closable="false"
            show-icon
            title="未检索到相关内容，请尝试更换关键词、扩大范围，或确认文档已建立词法索引。"
            style="margin-bottom: 12px;"
          />

          <el-alert
            v-if="result?.tabular_fallback && result?.tabular_fallback_reason"
            type="info"
            :closable="false"
            show-icon
            :title="`表格精确统计未命中：${result.tabular_fallback_reason}`"
            style="margin-bottom: 12px;"
          />

          <el-alert
            v-if="result?.message"
            type="warning"
            :closable="false"
            show-icon
            :title="result.message"
            style="margin-bottom: 12px;"
          />

          <el-alert
            v-else-if="result?.context_truncated"
            type="warning"
            :closable="false"
            show-icon
            :title="`检索到 ${result.hit_count} 条引用，合并上下文仅纳入前 ${result.context_chunk_count} 条，回答可能不完整`"
            style="margin-bottom: 12px;"
          />

          <div v-if="displayedAnswer" class="answer-panel">
            <div class="answer-label">{{ form.mode === 'smart' ? '回答' : '结构化结果' }}</div>
            <div class="answer-body">
              <MarkdownReport :content="displayedAnswer" compact />
            </div>
            <div v-if="result?.usage?.total_tokens" class="usage-meta">
              消耗约 {{ result.usage.total_tokens }} tokens · {{ Math.round((result.usage.duration_ms || 0) / 1000) }}s
            </div>
          </div>

          <div v-if="result?.tabular_basis" class="basis-card">
            <div class="basis-title">表格统计依据</div>
            <div class="basis-row">文档：{{ result.tabular_basis.document_title }}（#{{ result.tabular_basis.document_id }}）</div>
            <div v-if="result.tabular_basis.filter" class="basis-row">条件：{{ result.tabular_basis.filter }}</div>
            <div class="basis-row">
              命中 {{ result.tabular_basis.matched_count ?? '—' }} 条
              <span v-if="result.tabular_basis.total_rows != null"> / 源表共 {{ result.tabular_basis.total_rows }} 行</span>
              <span v-if="result.tabular_basis.rows_truncated && result.tabular_basis.stored_row_count != null">
                （已入库 {{ result.tabular_basis.stored_row_count }} 行，超出上限已截断）
              </span>
            </div>
          </div>

          <div v-if="result?.prose_basis?.sections_used?.length" class="basis-card">
            <div class="basis-title">长文档章节依据</div>
            <ul class="basis-list">
              <li v-for="(sec, idx) in result.prose_basis.sections_used" :key="idx">
                {{ sec.title }}
                <span v-if="sec.page != null">（第 {{ sec.page }} 页）</span>
              </li>
            </ul>
          </div>

          <el-table
            v-if="result?.matched_rows_preview?.length"
            :data="result.matched_rows_preview"
            stripe
            border
            size="small"
            class="chunks-table"
            style="margin-bottom: 12px;"
          >
            <el-table-column
              v-for="col in matchedPreviewColumns"
              :key="col"
              :prop="col"
              :label="col"
              min-width="120"
              show-overflow-tooltip
            />
          </el-table>

          <div v-if="groupByRows.length" class="basis-card">
            <div class="basis-title">分组统计</div>
            <el-table :data="groupByRows" stripe border size="small" class="chunks-table" style="margin-bottom: 12px;">
              <el-table-column prop="key" label="分组值" min-width="140" show-overflow-tooltip />
              <el-table-column prop="count" label="数量" width="88" align="center" />
            </el-table>
          </div>

          <el-collapse v-if="result?.sources?.length" v-model="sourcesOpen" class="result-collapse">
            <el-collapse-item name="sources" :title="`引用来源（${result.sources.length}）`">
              <div class="sources-grid">
                <div v-for="(src, idx) in result.sources" :key="`${src.document_id}-${src.chunk_index}`" class="source-card">
                  <div class="source-head">
                    <span class="source-idx">[来源{{ idx + 1 }}]</span>
                    <span class="source-doc">{{ src.title }}</span>
                  </div>
                  <div class="source-meta">
                    分块 #{{ (src.chunk_index || 0) + 1 }}
                    <span v-if="src.score != null"> · 相关度 {{ src.score }}</span>
                  </div>
                  <div v-if="src.text_preview" class="source-preview">
                    <KnowledgeChunkText :text="src.text_preview" :max-height="120" />
                  </div>
                </div>
              </div>
            </el-collapse-item>
          </el-collapse>

          <el-table
            v-if="form.mode === 'retrieve' && result?.chunks?.length"
            :data="result.chunks"
            stripe
            border
            size="small"
            class="chunks-table"
          >
            <el-table-column prop="title" label="文档" min-width="140" show-overflow-tooltip />
            <el-table-column label="分块" width="72" align="center">
              <template #default="{ row }">#{{ (row.chunk_index || 0) + 1 }}</template>
            </el-table-column>
            <el-table-column label="相关度" width="88" align="center">
              <template #default="{ row }">{{ row.score != null ? row.score : '—' }}</template>
            </el-table-column>
            <el-table-column label="片段" min-width="280">
              <template #default="{ row }">
                <KnowledgeChunkText :text="row.text" :max-height="200" />
              </template>
            </el-table-column>
          </el-table>

          <el-collapse v-if="result?.context_text" v-model="contextOpen" class="result-collapse">
            <el-collapse-item
              name="ctx"
              :title="form.mode === 'retrieve'
                ? `检索上下文（${contextBlocks.length} 段）`
                : `合并上下文预览（${contextBlocks.length} 段，LLM 实际读到的内容）`"
            >
              <div v-for="(block, idx) in contextBlocks" :key="idx" class="context-block">
                <div v-if="block.header" class="context-block-head">{{ block.header }}</div>
                <KnowledgeChunkText :text="block.body" :max-height="280" />
              </div>
            </el-collapse-item>
          </el-collapse>
        </el-card>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import { knowledgeApi } from '@/api/modules/knowledge.js'
import MarkdownReport from '@/components/MarkdownReport.vue'
import KnowledgeRefSelector from '@/modules/knowledge/components/KnowledgeRefSelector.vue'
import KnowledgeChunkText from '@/modules/knowledge/components/KnowledgeChunkText.vue'
import { formatQaAnswer, splitContextBlocks } from '@/modules/knowledge/utils/chunkTextFormat.js'
import { ProjectStore } from '@/stores/module/ProjectStore.js'
import { useKnowledgePermissions } from '@/modules/knowledge/composables/useKnowledgePermissions.js'

const route = useRoute()
const { canExecute: canRunKnowledge, canEdit } = useKnowledgePermissions()
const loadingHistory = ref(false)
const asking = ref(false)
const result = ref(null)
const contextOpen = ref([])
const sourcesOpen = ref([])

const contextBlocks = computed(() => splitContextBlocks(result.value?.context_text || ''))
const matchedPreviewColumns = computed(() => {
  const rows = result.value?.matched_rows_preview || []
  if (!rows.length || typeof rows[0] !== 'object') return []
  return Object.keys(rows[0])
})
const groupByRows = computed(() => {
  const groups = result.value?.group_by_result
  if (!groups || typeof groups !== 'object') return []
  return Object.entries(groups)
    .map(([key, count]) => ({ key, count: Number(count) || 0 }))
    .sort((a, b) => b.count - a.count || String(a.key).localeCompare(String(b.key), 'zh-CN'))
})
const displayedAnswer = ref('')
const historyItems = ref([])
const historyTotal = ref(0)
const activeRecordId = ref(null)
const selectedRecordIds = ref([])
const selectAll = ref(false)

const selectIndeterminate = computed(() => {
  const n = selectedRecordIds.value.length
  return n > 0 && n < historyItems.value.length
})

const projectId = computed(() => ProjectStore().projectInfo?.id)

const form = ref({
  mode: 'retrieve',
  query: '',
  scope: { folder_ids: [], document_ids: [] },
  top_k: 12
})

function buildScopePayload() {
  const docIds = (form.value.scope?.document_ids || []).filter(Boolean)
  const folderIds = (form.value.scope?.folder_ids || []).filter(Boolean)
  if (docIds.length) return { document_ids: docIds }
  if (folderIds.length) return { folder_ids: folderIds }
  return {}
}

function strategyLabel(s) {
  return {
    structured_tabular: '表格引擎',
    tabular_fallback: '表格未精确命中',
    tabular_fallback: '统计未命中',
    prose_fulltext: '全文注入',
    prose_section: '章节优先',
    layered_rag: '分层 RAG',
    rag: 'RAG 回退',
    lexical: '词法检索',
    vector: '向量检索',
    hybrid: '混合检索',
    fulltext: '全文回退',
    none: '无命中'
  }[s] || s
}

function strategyTag(s) {
  return {
    structured_tabular: 'success',
    tabular_fallback: 'warning',
    tabular_fallback: 'warning',
    prose_fulltext: 'primary',
    prose_section: 'primary',
    layered_rag: 'warning',
    rag: 'info',
    lexical: 'success',
    vector: 'primary',
    hybrid: 'warning',
    fulltext: 'warning',
    none: 'info'
  }[s] || 'info'
}

function formatTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const pad = n => String(n).padStart(2, '0')
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function applyResult(data) {
  result.value = data || null
  const isRetrieve = data?.mode === 'retrieve'
  contextOpen.value = isRetrieve && data?.context_text ? ['ctx'] : []
  sourcesOpen.value = isRetrieve && data?.sources?.length ? ['sources'] : []
  const ans = data?.answer || (data?.answer_path === 'structured_tabular' ? data?.context_text : '')
  if (ans && (data?.mode === 'smart' || data?.answer_path === 'structured_tabular' || data?.answer_path === 'tabular_fallback')) {
    displayedAnswer.value = formatQaAnswer(ans)
  } else {
    displayedAnswer.value = ''
  }
}

function resetForm() {
  activeRecordId.value = null
  form.value = {
    mode: form.value.mode,
    query: '',
    scope: { folder_ids: [], document_ids: [] },
    top_k: 12
  }
  result.value = null
  displayedAnswer.value = ''
  contextOpen.value = []
  sourcesOpen.value = []
}

async function loadHistory() {
  if (!projectId.value) {
    historyItems.value = []
    historyTotal.value = 0
    selectedRecordIds.value = []
    selectAll.value = false
    return
  }
  loadingHistory.value = true
  try {
    const res = await knowledgeApi.listQaRecords(projectId.value, { page: 1, size: 30 })
    historyItems.value = res.data?.items || []
    historyTotal.value = res.data?.total || 0
    const visible = new Set(historyItems.value.map(i => i.id))
    selectedRecordIds.value = selectedRecordIds.value.filter(id => visible.has(id))
    selectAll.value = historyItems.value.length > 0 && selectedRecordIds.value.length === historyItems.value.length
  } catch (e) {
    console.warn('加载问答历史失败', e)
  } finally {
    loadingHistory.value = false
  }
}

function toggleRecordSelect(recordId, checked) {
  const ids = new Set(selectedRecordIds.value)
  if (checked) ids.add(recordId)
  else ids.delete(recordId)
  selectedRecordIds.value = [...ids]
  selectAll.value = historyItems.value.length > 0 && ids.size === historyItems.value.length
}

function toggleSelectAll(checked) {
  selectedRecordIds.value = checked ? historyItems.value.map(i => i.id) : []
  selectAll.value = !!checked
}

async function batchRemoveRecords() {
  if (!projectId.value || !selectedRecordIds.value.length) return
  const count = selectedRecordIds.value.length
  try {
    await ElMessageBox.confirm(`确定删除选中的 ${count} 条问答记录？`, '批量删除', { type: 'warning' })
    const res = await knowledgeApi.batchDeleteQaRecords(selectedRecordIds.value, projectId.value)
    const deleted = res.data?.deleted_count ?? count
    if (selectedRecordIds.value.includes(activeRecordId.value)) {
      activeRecordId.value = null
    }
    selectedRecordIds.value = []
    selectAll.value = false
    ElMessage.success(`已删除 ${deleted} 条`)
    await loadHistory()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e?.message || '批量删除失败')
  }
}

async function restoreRecord(recordId) {
  if (!projectId.value || activeRecordId.value === recordId) return
  try {
    const res = await knowledgeApi.getQaRecord(recordId, projectId.value)
    const detail = res.data || {}
    activeRecordId.value = recordId
    form.value = {
      mode: detail.mode === 'smart' ? 'smart' : 'retrieve',
      query: detail.query || '',
      scope: {
        folder_ids: Array.isArray(detail.folder_ids) ? [...detail.folder_ids] : [],
        document_ids: Array.isArray(detail.document_ids) ? [...detail.document_ids] : []
      },
      top_k: detail.top_k || 12
    }
    const payload = detail.result && typeof detail.result === 'object' ? detail.result : detail
    applyResult(payload)
  } catch (e) {
    ElMessage.error(e?.message || '加载历史失败')
  }
}

async function removeRecord(item) {
  if (!projectId.value) return
  try {
    await ElMessageBox.confirm(`确定删除这条问答记录？\n「${item.query}」`, '确认', { type: 'warning' })
    await knowledgeApi.deleteQaRecord(item.id, projectId.value)
    if (activeRecordId.value === item.id) {
      activeRecordId.value = null
    }
    ElMessage.success('已删除')
    await loadHistory()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e?.message || '删除失败')
  }
}

async function ask() {
  const q = (form.value.query || '').trim()
  if (!projectId.value) {
    ElMessage.warning('请先选择项目')
    return
  }
  if (!q) {
    ElMessage.warning('请输入问题')
    return
  }
  if (form.value.mode === 'smart' && !canRunKnowledge.value) {
    ElMessage.warning('智能模式需要「资料库-执行」权限')
    return
  }

  displayedAnswer.value = ''
  result.value = null
  contextOpen.value = []
  sourcesOpen.value = []
  activeRecordId.value = null
  asking.value = true
  try {
    const res = await knowledgeApi.askKnowledge(
      {
        mode: form.value.mode,
        query: q,
        top_k: form.value.top_k,
        max_chars: 48000,
        ...buildScopePayload()
      },
      projectId.value
    )
    applyResult(res.data || null)
    if (res.data?.record_id) {
      activeRecordId.value = res.data.record_id
    }
    await loadHistory()
  } catch (e) {
    ElMessage.error(e?.message || '问答失败')
  } finally {
    asking.value = false
  }
}

onMounted(async () => {
  await loadHistory()
  const q = route.query.q
  if (typeof q === 'string' && q.trim()) {
    form.value.query = q.trim()
  }
  const fid = route.query.folder_id
  if (fid) {
    const n = Number(fid)
    if (n) form.value.scope.folder_ids = [n]
  }
  const mode = route.query.mode
  if (mode === 'smart' || mode === 'retrieve') {
    form.value.mode = mode
  }
  if (form.value.query) {
    await ask()
  }
})

</script>

<style scoped>
.knowledge-qa {
  min-height: 100%;
}
.qa-layout {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}
.history-panel {
  flex: 0 0 280px;
  max-width: 280px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-fill-color-blank);
  padding: 12px;
  max-height: calc(100vh - 180px);
  overflow: auto;
  position: sticky;
  top: 12px;
}
.history-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
  font-size: 14px;
}
.history-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 4px 8px;
}
.history-actions :deep(.el-checkbox) {
  margin-right: 0;
}
.history-actions :deep(.el-checkbox__label) {
  font-size: 12px;
  padding-left: 4px;
}
.history-empty {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  padding: 16px 4px;
  line-height: 1.6;
}
.history-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.history-item {
  position: relative;
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 10px;
  margin-bottom: 8px;
  border-radius: 8px;
  border: 1px solid var(--el-border-color-lighter);
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}
.history-item.selected {
  border-color: var(--el-color-danger-light-5);
  background: var(--el-color-danger-light-9);
}
.history-check {
  flex-shrink: 0;
  margin-top: 2px;
  height: auto;
}
.history-item-body {
  flex: 1;
  min-width: 0;
  position: relative;
}
.history-item:hover {
  border-color: var(--el-color-primary-light-5);
  background: var(--el-fill-color-light);
}
.history-item.active {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}
.history-item-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  margin-bottom: 6px;
}
.history-time {
  font-size: 11px;
  color: var(--el-text-color-secondary);
}
.history-query {
  font-size: 13px;
  font-weight: 500;
  line-height: 1.45;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.history-preview {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.history-meta {
  margin-top: 6px;
  font-size: 11px;
  color: var(--el-text-color-secondary);
}
.history-del {
  position: absolute;
  right: 4px;
  bottom: 4px;
  opacity: 0;
  transition: opacity 0.15s;
}
.history-item:hover .history-del {
  opacity: 1;
}
.history-more {
  margin-top: 8px;
  font-size: 11px;
  color: var(--el-text-color-secondary);
  text-align: center;
}
.qa-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.mode-hint {
  margin-top: 8px;
  margin-left: 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}
.scope-tip {
  margin: -8px 0 4px 88px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.55;
}
.result-card {
  margin-top: 0;
}
.result-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.result-meta {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.waiting-box {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 0 16px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.answer-panel {
  margin-bottom: 16px;
}
.basis-card {
  margin-bottom: 12px;
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--el-fill-color-lighter);
  font-size: 13px;
}
.basis-title {
  font-weight: 600;
  margin-bottom: 6px;
}
.basis-row {
  color: var(--el-text-color-regular);
  line-height: 1.6;
}
.basis-list {
  margin: 0;
  padding-left: 18px;
  color: var(--el-text-color-regular);
}
.answer-label {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 8px;
}
.answer-body {
  padding: 12px 14px;
  border-radius: 8px;
  background: var(--el-fill-color-light);
  font-size: 14px;
  line-height: 1.75;
}
.usage-meta {
  margin-top: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.result-collapse {
  margin-top: 12px;
  border: none;
}
.result-collapse :deep(.el-collapse-item__header) {
  font-weight: 600;
  font-size: 13px;
}
.sources-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.source-card {
  flex: 1 1 220px;
  max-width: 320px;
  padding: 10px 12px;
  border-radius: 8px;
  border: 1px solid var(--el-border-color-lighter);
  background: var(--el-fill-color-blank);
}
.source-head {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin-bottom: 4px;
}
.source-idx {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--el-color-primary);
  font-weight: 600;
}
.source-doc {
  font-size: 13px;
  font-weight: 500;
  line-height: 1.4;
}
.source-meta {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  margin-bottom: 6px;
}
.source-preview {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-regular);
  line-height: 1.5;
}
.chunks-table {
  margin-top: 8px;
}
.context-block {
  margin-bottom: 14px;
}
.context-block:last-child {
  margin-bottom: 0;
}
.context-block-head {
  margin-bottom: 8px;
  font-size: 12px;
  font-weight: 600;
  color: var(--el-color-primary);
}
@media (max-width: 960px) {
  .qa-layout {
    flex-direction: column;
  }
  .history-panel {
    flex: none;
    max-width: none;
    width: 100%;
    max-height: 240px;
    position: static;
  }
}
</style>
