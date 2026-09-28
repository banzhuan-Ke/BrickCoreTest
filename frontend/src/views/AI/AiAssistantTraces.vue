<template>
  <PageCard>
    <template #title>
      <b>小测回合追踪</b>
    </template>
    <template #main>
      <div class="traces-page" v-loading="loading">
        <el-alert
          title="仅展示脱敏元数据（工具名、技能码、耗时、停止原因等），不含 Prompt、用户正文或工具参数。含小测对话与技能快捷入口；历史仅对话主路径有记录。"
          type="info"
          show-icon
          :closable="false"
          class="hint-alert"
        />

        <div class="toolbar">
          <el-checkbox
            v-model="onlyCurrentProject"
            :disabled="!proStore.projectInfo?.id"
            @change="onFilterChange"
          >
            仅当前项目{{ currentProjectLabel || '（请先选择项目）' }}
          </el-checkbox>
          <el-input
            v-model="sessionIdFilter"
            clearable
            placeholder="会话 ID"
            style="width: 140px"
            @clear="onFilterChange"
            @keyup.enter="onFilterChange"
          />
          <el-button type="primary" @click="onFilterChange">查询</el-button>
          <el-button @click="load">刷新</el-button>
          <el-button link type="primary" @click="router.push('/ai-skills')">技能与助手</el-button>
        </div>

        <el-table :data="items" stripe border size="small" empty-text="暂无追踪记录">
          <el-table-column prop="id" label="ID" width="80" />
          <el-table-column prop="create_time" label="时间" min-width="160">
            <template #default="{ row }">{{ formatTime(row.create_time) }}</template>
          </el-table-column>
          <el-table-column prop="mode" label="模式" width="90" />
          <el-table-column prop="session_id" label="会话" width="90" />
          <el-table-column label="项目" min-width="140" show-overflow-tooltip>
            <template #default="{ row }">{{ row.project_name || (row.project_id != null ? `#${row.project_id}` : '—') }}</template>
          </el-table-column>
          <el-table-column label="用户" min-width="140" show-overflow-tooltip>
            <template #default="{ row }">{{ row.user_display || (row.user_id != null ? `#${row.user_id}` : '—') }}</template>
          </el-table-column>
          <el-table-column prop="stop_reason" label="停止原因" min-width="120" show-overflow-tooltip />
          <el-table-column prop="rounds" label="轮次" width="70" />
          <el-table-column prop="tokens_used" label="Tokens" width="90" />
          <el-table-column prop="duration_ms" label="耗时(ms)" width="100" />
          <el-table-column label="工具" min-width="160" show-overflow-tooltip>
            <template #default="{ row }">{{ (row.tools_used || []).join(', ') || '—' }}</template>
          </el-table-column>
          <el-table-column label="技能" min-width="140" show-overflow-tooltip>
            <template #default="{ row }">{{ skillSummary(row.skills_used) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="90" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="openDetail(row)">详情</el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="pager">
          <el-pagination
            v-model:current-page="page"
            v-model:page-size="pageSize"
            :total="total"
            :page-sizes="[20, 50, 100]"
            layout="total, sizes, prev, pager, next"
            background
            @current-change="load"
            @size-change="onPageSizeChange"
          />
        </div>

        <el-drawer v-model="detailOpen" title="追踪详情" size="420px" append-to-body>
          <div v-loading="detailLoading" class="detail-body">
            <template v-if="detail">
              <el-descriptions :column="1" border size="small">
                <el-descriptions-item label="ID">{{ detail.id }}</el-descriptions-item>
                <el-descriptions-item label="时间">{{ formatTime(detail.create_time) }}</el-descriptions-item>
                <el-descriptions-item label="模式">{{ detail.mode || '—' }}</el-descriptions-item>
                <el-descriptions-item label="会话">{{ detail.session_id ?? '—' }}</el-descriptions-item>
                <el-descriptions-item label="用户">
                  {{ detail.user_display || (detail.user_id != null ? `#${detail.user_id}` : '—') }}
                </el-descriptions-item>
                <el-descriptions-item label="项目">
                  {{ detail.project_name || (detail.project_id != null ? `#${detail.project_id}` : '—') }}
                </el-descriptions-item>
                <el-descriptions-item label="停止原因">{{ detail.stop_reason || '—' }}</el-descriptions-item>
                <el-descriptions-item label="错误码">{{ detail.error_code || '—' }}</el-descriptions-item>
                <el-descriptions-item label="轮次">{{ detail.rounds ?? '—' }}</el-descriptions-item>
                <el-descriptions-item label="Tokens">{{ detail.tokens_used ?? '—' }}</el-descriptions-item>
                <el-descriptions-item label="耗时(ms)">{{ detail.duration_ms ?? '—' }}</el-descriptions-item>
                <el-descriptions-item label="待确认">
                  {{ detail.has_pending_confirm ? '是' : '否' }}
                </el-descriptions-item>
                <el-descriptions-item label="待追问">
                  {{ detail.has_pending_ask_user ? '是' : '否' }}
                </el-descriptions-item>
                <el-descriptions-item label="工具">
                  {{ (detail.tools_used || []).join(', ') || '—' }}
                </el-descriptions-item>
                <el-descriptions-item label="技能">
                  {{ skillSummary(detail.skills_used) }}
                </el-descriptions-item>
              </el-descriptions>
            </template>
            <el-empty v-else-if="!detailLoading" description="无详情" :image-size="64" />
          </div>
        </el-drawer>
      </div>
    </template>
  </PageCard>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import PageCard from '@/components/PageCard.vue'
import { aiAssistantApi } from '@/api/modules/ai_assistant.js'
import { ProjectStore } from '@/stores/module/ProjectStore.js'

const router = useRouter()
const proStore = ProjectStore()

const loading = ref(false)
const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(50)
const onlyCurrentProject = ref(true)
const sessionIdFilter = ref('')

const detailOpen = ref(false)
const detailLoading = ref(false)
const detail = ref(null)

const currentProjectLabel = computed(() => {
  const p = proStore.projectInfo
  if (!p?.id) return ''
  return p.name ? `（${p.name}）` : `（#${p.id}）`
})

function formatTime(v) {
  if (!v) return '—'
  try {
    return new Date(v).toLocaleString()
  } catch {
    return String(v)
  }
}

function skillSummary(skills) {
  if (!Array.isArray(skills) || !skills.length) return '—'
  return skills
    .map((s) => {
      if (typeof s === 'string') return s
      const code = s?.code || ''
      const status = s?.status ? `:${s.status}` : ''
      return `${code}${status}`
    })
    .filter(Boolean)
    .join(', ')
}

function onFilterChange() {
  page.value = 1
  load()
}

function onPageSizeChange() {
  page.value = 1
  load()
}

async function load() {
  loading.value = true
  try {
    const sidRaw = String(sessionIdFilter.value || '').trim()
    const sessionId = sidRaw && /^\d+$/.test(sidRaw) ? Number(sidRaw) : null
    const projectId =
      onlyCurrentProject.value && proStore.projectInfo?.id ? proStore.projectInfo.id : null
    const res = await aiAssistantApi.listTraces({
      projectId,
      sessionId,
      limit: pageSize.value,
      offset: (page.value - 1) * pageSize.value
    })
    if (res.data?.code === 200) {
      const data = res.data.data || {}
      items.value = data.items || []
      total.value = data.total || 0
    } else {
      throw new Error(res.data?.message || '加载失败')
    }
  } catch (e) {
    items.value = []
    total.value = 0
    const detailMsg = e?.response?.data?.detail || e?.message || '加载失败'
    ElMessage.error(typeof detailMsg === 'string' ? detailMsg : '加载失败')
  } finally {
    loading.value = false
  }
}

async function openDetail(row) {
  detailOpen.value = true
  detail.value = row || null
  if (!row?.id) return
  detailLoading.value = true
  try {
    const res = await aiAssistantApi.getTrace(row.id)
    if (res.data?.code === 200) {
      detail.value = res.data.data || row
    }
  } catch (e) {
    const detailMsg = e?.response?.data?.detail || e?.message || '加载详情失败'
    ElMessage.error(typeof detailMsg === 'string' ? detailMsg : '加载详情失败')
  } finally {
    detailLoading.value = false
  }
}

onMounted(() => {
  if (!proStore.projectInfo?.id) onlyCurrentProject.value = false
  load()
})
</script>

<style scoped>
.traces-page {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.hint-alert {
  margin-bottom: 0;
}
.toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}
.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 4px;
}
.detail-body {
  min-height: 120px;
}
</style>
