<template>
  <PageCard>
    <template #title>
      <b>生成用例审核</b>
    </template>
    <template #main>
      <div class="review-page" v-loading="loading">
        <el-alert
          title="需求/测试点生成的用例默认为「待审核」。通过后方可入库到功能用例库；与版本里的「用例评审」不是同一流程。"
          type="info"
          show-icon
          :closable="false"
          class="hint"
        />

        <div class="toolbar">
          <el-select v-model="statusFilter" style="width: 140px" @change="onFilterChange">
            <el-option label="待审核" value="pending" />
            <el-option label="已通过" value="approved" />
            <el-option label="已驳回" value="rejected" />
          </el-select>
          <el-input
            v-model="requirementIdFilter"
            clearable
            placeholder="需求 ID"
            style="width: 140px"
            @clear="onFilterChange"
            @keyup.enter="onFilterChange"
          />
          <el-button type="primary" @click="onFilterChange">查询</el-button>
          <el-button @click="load">刷新</el-button>
          <el-button
            type="success"
            :disabled="!selectedIds.length"
            :loading="acting"
            @click="reviewSelected('approved')"
          >
            通过 ({{ selectedIds.length }})
          </el-button>
          <el-button
            type="danger"
            plain
            :disabled="!selectedIds.length"
            :loading="acting"
            @click="reviewSelected('rejected')"
          >
            驳回
          </el-button>
        </div>

        <el-table
          :data="items"
          border
          stripe
          size="small"
          empty-text="暂无待审用例"
          @selection-change="onSelectionChange"
        >
          <el-table-column type="selection" width="48" />
          <el-table-column prop="id" label="ID" width="72" />
          <el-table-column prop="requirement_name" label="需求" min-width="140" show-overflow-tooltip />
          <el-table-column prop="title" label="用例标题" min-width="220" show-overflow-tooltip />
          <el-table-column prop="module" label="模块" width="120" show-overflow-tooltip />
          <el-table-column prop="priority" label="优先级" width="72" align="center" />
          <el-table-column label="质检" min-width="140" show-overflow-tooltip>
            <template #default="{ row }">
              <el-tag v-if="!row.quality_checks" size="small" type="info">未检</el-tag>
              <el-tag
                v-else-if="(row.quality_severity || 'ok') === 'ok'"
                size="small"
                type="success"
              >通过</el-tag>
              <el-tag
                v-else
                size="small"
                :type="row.quality_severity === 'error' ? 'danger' : 'warning'"
              >{{ row.quality_summary || '有问题' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="110" align="center">
            <template #default="{ row }">
              <el-tag :type="statusTagType(row.status)" size="small">
                {{ row.status_label || row.status }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="create_by" label="生成人" width="90" show-overflow-tooltip />
          <el-table-column prop="create_time" label="时间" width="160" />
          <el-table-column label="操作" width="200" fixed="right">
            <template #default="{ row }">
              <el-button
                v-if="isPending(row.status)"
                link
                type="success"
                @click="reviewOne(row, 'approved')"
              >
                通过
              </el-button>
              <el-button
                v-if="isPending(row.status)"
                link
                type="danger"
                @click="reviewOne(row, 'rejected')"
              >
                驳回
              </el-button>
              <el-button link type="primary" @click="openRequirement(row)">打开需求</el-button>
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
      </div>
    </template>
  </PageCard>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import PageCard from '@/components/PageCard.vue'
import { aiRequirementApi } from '@/api/modules/ai.js'
import { ProjectStore } from '@/stores/module/ProjectStore.js'

const route = useRoute()
const router = useRouter()
const proStore = ProjectStore()

const loading = ref(false)
const acting = ref(false)
const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(50)
const statusFilter = ref('pending')
const requirementIdFilter = ref('')
const selectedIds = ref([])

function isPending(status) {
  return status === 'needs_review' || status === 'draft'
}

function statusTagType(status) {
  if (status === 'approved' || status === 'confirmed' || status === 'exported') return 'success'
  if (status === 'rejected') return 'danger'
  return 'warning'
}

function onSelectionChange(rows) {
  selectedIds.value = (rows || []).map((r) => r.id)
}

function onFilterChange() {
  page.value = 1
  load()
}

function onPageSizeChange() {
  page.value = 1
  load()
}

function openRequirement(row) {
  if (!row?.requirement_id) return
  router.push({
    path: `/ai-testing/requirements/${row.requirement_id}`,
    query: { tab: 'cases' }
  })
}

async function load() {
  if (!proStore.projectInfo?.id) {
    items.value = []
    total.value = 0
    ElMessage.warning('请先选择项目')
    return
  }
  loading.value = true
  try {
    const sid = String(requirementIdFilter.value || '').trim()
    const requirementId = sid && /^\d+$/.test(sid) ? Number(sid) : null
    const res = await aiRequirementApi.listCaseReviewQueue({
      project_id: proStore.projectInfo.id,
      status: statusFilter.value,
      requirement_id: requirementId,
      limit: pageSize.value,
      offset: (page.value - 1) * pageSize.value
    })
    if (res.data?.code === 200) {
      items.value = res.data.data?.items || []
      total.value = res.data.data?.total || 0
    } else {
      throw new Error(res.data?.message || '加载失败')
    }
  } catch (e) {
    items.value = []
    total.value = 0
    const msg = e?.response?.data?.detail || e?.message || '加载失败'
    ElMessage.error(typeof msg === 'string' ? msg : '加载失败')
  } finally {
    loading.value = false
  }
}

async function doReview(ids, decision) {
  if (!ids.length || !proStore.projectInfo?.id) return
  let note = ''
  let reasonTag = ''
  const reasonTags = [
    '规则理解错误',
    '遗漏场景',
    '重复',
    '步骤不可执行',
    '预期不可验证',
    '优先级不合理',
    '需求本身不明确',
    '其他'
  ]
  if (decision === 'rejected') {
    try {
      const { value } = await ElMessageBox.prompt(
        `请填写原因标签：${reasonTags.join('、')}`,
        '驳回用例',
        {
          confirmButtonText: '驳回',
          cancelButtonText: '取消',
          inputPlaceholder: '例如：步骤不可执行',
          inputValidator: (v) => {
            const t = (v || '').trim()
            if (!t) return '驳回须填写原因标签'
            if (!reasonTags.includes(t)) return `请使用标准标签`
            return true
          }
        }
      )
      reasonTag = (value || '').trim()
    } catch {
      return
    }
    try {
      const { value } = await ElMessageBox.prompt('可选：补充说明', '驳回备注', {
        confirmButtonText: '确定',
        cancelButtonText: '跳过备注',
        inputPlaceholder: '备注'
      })
      note = value || ''
    } catch {
      note = ''
    }
  }
  acting.value = true
  try {
    const res = await aiRequirementApi.reviewCases({
      caseIds: ids,
      decision,
      note,
      reasonTag,
      projectId: proStore.projectInfo.id
    })
    if (res.data?.code === 200) {
      ElMessage.success(res.data.message || '已更新')
      selectedIds.value = []
      await load()
    } else {
      throw new Error(res.data?.message || '操作失败')
    }
  } catch (e) {
    const msg = e?.response?.data?.detail || e?.message || '操作失败'
    ElMessage.error(typeof msg === 'string' ? msg : '操作失败')
  } finally {
    acting.value = false
  }
}

async function reviewSelected(decision) {
  await doReview(selectedIds.value, decision)
}

async function reviewOne(row, decision) {
  if (!row?.id) return
  await doReview([row.id], decision)
}

onMounted(() => {
  const q = route.query?.requirement_id
  if (q) requirementIdFilter.value = String(q)
  load()
})
</script>

<style scoped>
.review-page {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.hint {
  margin: 0;
}
.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.pager {
  display: flex;
  justify-content: flex-end;
}
</style>
