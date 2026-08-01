<template>
  <div class="knowledge-search">
    <el-card shadow="never">
      <el-form :model="form" label-width="88px" @submit.prevent>
        <el-form-item label="检索问题" required>
          <el-input
            v-model="form.query"
            type="textarea"
            :rows="2"
            maxlength="500"
            show-word-limit
            placeholder="例如：登录失败根因、支付模块历史缺陷、本轮测试范围"
            @keyup.enter.ctrl="runSearch"
          />
        </el-form-item>
        <KnowledgeRefSelector
          v-model="form.scope"
          label="限定范围"
          hint="先选迭代文件夹，下方会列出该文件夹内文档，可勾选其中几份缩小检索范围"
          :show-estimate="false"
          :show-ref-cards="false"
          :show-retrieve-preview="false"
          folder-placeholder="选择迭代文件夹（推荐）"
        />
        <div class="scope-tip">
          不勾选文档则检索整个文件夹；文件夹也不选则检索项目内全部已索引资料。
        </div>
        <el-form-item label="返回条数">
          <el-input-number v-model="form.top_k" :min="1" :max="30" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="searching" @click="runSearch">检索</el-button>
          <el-button @click="resetForm">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card v-if="result" shadow="never" class="result-card">
      <template #header>
        <div class="result-head">
          <b>检索结果</b>
          <el-tag size="small" :type="strategyTag(result.strategy)">{{ strategyLabel(result.strategy) }}</el-tag>
          <span class="result-meta">
            {{ result.hit_count || 0 }} 条命中 · {{ result.doc_count || 0 }} 篇文档
          </span>
        </div>
      </template>

      <el-alert
        v-if="result.message"
        type="info"
        :closable="false"
        show-icon
        :title="result.message"
        style="margin-bottom: 12px;"
      />

      <el-table v-if="result.chunks?.length" :data="result.chunks" stripe border size="small">
        <el-table-column prop="title" label="文档" min-width="140" show-overflow-tooltip />
        <el-table-column label="分块" width="72" align="center">
          <template #default="{ row }">#{{ (row.chunk_index || 0) + 1 }}</template>
        </el-table-column>
        <el-table-column label="相关度" width="88" align="center">
          <template #default="{ row }">
            {{ row.score != null ? row.score : '—' }}
          </template>
        </el-table-column>
        <el-table-column label="片段" min-width="320">
          <template #default="{ row }">
            <KnowledgeChunkText :text="row.text" :max-height="220" />
          </template>
        </el-table-column>
      </el-table>

      <el-collapse v-if="result.context_text" v-model="contextOpen" class="context-collapse">
        <el-collapse-item name="ctx" title="合并上下文（送入 AI 的文本预览）">
          <div v-for="(block, idx) in contextBlocks" :key="idx" class="context-block">
            <div v-if="block.header" class="context-block-head">{{ block.header }}</div>
            <KnowledgeChunkText :text="block.body" :max-height="360" />
          </div>
        </el-collapse-item>
      </el-collapse>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { knowledgeApi } from '@/api/modules/knowledge.js'
import KnowledgeRefSelector from '@/modules/knowledge/components/KnowledgeRefSelector.vue'
import KnowledgeChunkText from '@/modules/knowledge/components/KnowledgeChunkText.vue'
import { splitContextBlocks } from '@/modules/knowledge/utils/chunkTextFormat.js'
import { ProjectStore } from '@/stores/module/ProjectStore.js'

const route = useRoute()
const searching = ref(false)
const result = ref(null)
const contextOpen = ref([])

const contextBlocks = computed(() => splitContextBlocks(result.value?.context_text || ''))

const form = ref({
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
    lexical: '词法检索',
    vector: '向量检索',
    hybrid: '混合检索',
    rag: 'RAG 分块',
    fulltext: '全文回退',
    none: '无命中'
  }[s] || s
}

function strategyTag(s) {
  return { lexical: 'success', vector: 'primary', hybrid: 'warning', rag: 'success', fulltext: 'warning', none: 'info' }[s] || 'info'
}

function resetForm() {
  form.value = { query: '', scope: { folder_ids: [], document_ids: [] }, top_k: 12 }
  result.value = null
}

async function runSearch() {
  const pid = ProjectStore().projectInfo?.id
  const q = (form.value.query || '').trim()
  if (!pid) {
    ElMessage.warning('请先选择项目')
    return
  }
  if (!q) {
    ElMessage.warning('请输入检索问题')
    return
  }
  searching.value = true
  try {
    const res = await knowledgeApi.retrieveKnowledge(
      {
        query: q,
        top_k: form.value.top_k,
        max_chars: 48000,
        ...buildScopePayload()
      },
      pid
    )
    result.value = res.data || null
  } catch (e) {
    ElMessage.error(e?.message || '检索失败')
  } finally {
    searching.value = false
  }
}

onMounted(async () => {
  const q = route.query.q
  if (typeof q === 'string' && q.trim()) {
    form.value.query = q.trim()
  }
  const fid = route.query.folder_id
  if (fid) {
    const n = Number(fid)
    if (n) form.value.scope.folder_ids = [n]
  }
  if (form.value.query) {
    await runSearch()
  }
})
</script>

<style scoped>
.knowledge-search {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.scope-tip {
  margin: -8px 0 8px 88px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.55;
}
.result-card {
  margin-top: 4px;
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
.context-collapse {
  margin-top: 12px;
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
</style>
