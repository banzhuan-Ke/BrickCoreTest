<template>
  <div class="tm-review-detail" v-loading="loading">
    <div class="header" v-if="review">
      <TmBackButton @click="goBack" />
      <h2>{{ review.title }}</h2>
      <el-tag :type="statusTagType(review.status)">{{ statusLabel(review.status) }}</el-tag>
      <div class="actions">
        <el-button
          v-if="canCancelReview && ['pending', 'in_review'].includes(review.status)"
          type="danger"
          plain
          @click="cancelReview"
        >取消评审</el-button>
      </div>
    </div>

    <div class="stats-bar" v-if="stats">
      <div class="stat-chip">
        <span class="lab">用例</span>
        <span>{{ stats.items?.total || 0 }}</span>
      </div>
      <div class="stat-chip ok">
        <span class="lab">通过</span>
        <span>{{ stats.items?.approved || 0 }}</span>
      </div>
      <div class="stat-chip warn">
        <span class="lab">需修改</span>
        <span>{{ stats.items?.changes_requested || 0 }}</span>
      </div>
      <div class="stat-chip bad">
        <span class="lab">拒绝</span>
        <span>{{ stats.items?.rejected || 0 }}</span>
      </div>
      <div class="stat-chip">
        <span class="lab">待评</span>
        <span>{{ stats.items?.pending || 0 }}</span>
      </div>
      <div class="reviewer-progress" v-if="(stats.reviewers || []).length">
        <span
          v-for="r in stats.reviewers"
          :key="r.reviewer_id"
          class="rev-pill"
          :class="{ done: r.complete }"
        >
          {{ memberLabel(r.reviewer_id) }} {{ r.done }}/{{ r.total }}
        </span>
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="agg-hint"
      title="多人评审：每条用例汇总所有评审人结论（任一人拒绝/需修改则整体不通过，全部必评人通过才算通过）。版本负责人可对单条用例定版。"
    />

    <el-table :data="items" border stripe class="review-table">
      <el-table-column prop="functional_case_id" label="用例ID" width="90" />
      <el-table-column prop="case_title" label="标题" min-width="200" show-overflow-tooltip />
      <el-table-column label="汇总结论" width="120">
        <template #default="{ row }">
          <el-tag size="small" :type="decisionTagType(displayDecision(row))">
            {{ decisionLabel(displayDecision(row)) }}
          </el-tag>
          <el-tag
            v-if="row.owner_decision"
            size="small"
            type="success"
            effect="plain"
            class="owner-tag"
          >已定版</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="各人结论" min-width="280">
        <template #default="{ row }">
          <div class="decision-list">
            <div
              v-for="d in row.decisions_json || []"
              :key="`${d.reviewer_id}-${d.decision}`"
              class="decision-row"
            >
              <span class="who">{{ memberLabel(d.reviewer_id) }}</span>
              <el-tag size="small" :type="decisionTagType(d.decision)">
                {{ decisionLabel(d.decision) }}
              </el-tag>
              <span v-if="d.comment" class="cmt" :title="d.comment">{{ d.comment }}</span>
              <span v-if="(d.attachments || []).length" class="att">
                {{ (d.attachments || []).length }} 附件
              </span>
            </div>
            <div
              v-for="rid in pendingReviewers(row)"
              :key="`p-${rid}`"
              class="decision-row pending"
            >
              <span class="who">{{ memberLabel(rid) }}</span>
              <el-tag size="small" type="info">待评</el-tag>
            </div>
            <span v-if="!(row.decisions_json || []).length && !pendingReviewers(row).length">—</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="comment" label="意见摘要" min-width="140" show-overflow-tooltip />
      <el-table-column label="操作" width="280" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openViewCase(row)">查看用例</el-button>
          <el-button
            v-if="canSubmit"
            link
            type="primary"
            :disabled="!!row.owner_decision || review?.status === 'cancelled'"
            @click="openDecide(row)"
          >提交结论</el-button>
          <el-button
            v-if="canFinalizeItem(row)"
            link
            type="warning"
            @click="openItemFinalize(row)"
          >负责人定版</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="decideVisible" title="提交评审结论" width="640px" destroy-on-close>
      <FunctionalCaseBodyPanel
        v-if="decideItem"
        :case-data="decideCaseData"
        :functional-case-id="decideItem.functional_case_id"
        :project-id="projectId"
        class="case-preview"
      />
      <el-form label-width="90px" class="decide-form">
        <el-form-item v-if="checklistItems.length" label="检查清单">
          <div class="checklist-box">
            <div v-for="c in checklistItems" :key="c.key" class="check-row">
              <el-checkbox v-model="decideForm.checklist[c.key]">
                {{ c.label || c.key }}
                <el-tag v-if="c.required" size="small" type="danger" effect="plain">必填</el-tag>
              </el-checkbox>
            </div>
          </div>
        </el-form-item>
        <el-form-item label="结论" required>
          <el-select v-model="decideForm.decision" style="width: 200px">
            <el-option label="通过" value="approved" />
            <el-option label="需修改" value="changes_requested" />
            <el-option label="拒绝" value="rejected" />
          </el-select>
        </el-form-item>
        <el-form-item label="意见">
          <el-input
            v-model="decideForm.comment"
            type="textarea"
            :rows="4"
            placeholder="说明通过/不通过的理由，可粘贴截图后点下方上传"
          />
        </el-form-item>
        <el-form-item label="截图/附件">
          <DefectAttachments
            v-if="projectId"
            v-model="decideForm.attachments"
            :project-id="projectId"
            :api="reviewAttachmentApi"
            :max-count="10"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="decideVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitDecide">提交</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="viewCaseVisible" title="用例正文" size="560px" destroy-on-close>
      <FunctionalCaseBodyPanel
        v-if="viewCaseRow"
        :case-data="viewCaseData"
        :functional-case-id="viewCaseRow.functional_case_id"
        :project-id="projectId"
      />
    </el-drawer>

    <el-dialog v-model="itemFinalizeVisible" title="版本负责人 · 单条定版" width="480px" destroy-on-close>
      <el-alert
        type="warning"
        :closable="false"
        show-icon
        style="margin-bottom: 12px"
        title="定版后评审人不可再改该用例结论。"
      />
      <div v-if="finalizeItemRow" class="finalize-case">
        用例 #{{ finalizeItemRow.functional_case_id }}
        <span v-if="finalizeItemRow.case_title">· {{ finalizeItemRow.case_title }}</span>
      </div>
      <el-form label-width="90px">
        <el-form-item label="定版结论" required>
          <el-select v-model="itemFinalizeForm.decision" style="width: 220px">
            <el-option label="通过" value="approved" />
            <el-option label="需修改" value="changes_requested" />
            <el-option label="驳回" value="rejected" />
          </el-select>
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="itemFinalizeForm.comment" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="itemFinalizeVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitItemFinalize">确认定版</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { testReviewApi } from '@/api/testManagement'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { UserStore } from '@/stores/module/UserStore'
import { formatMemberName, loadMemberNameMap } from '@/utils/projectMembers'
import DefectAttachments from './components/DefectAttachments.vue'
import FunctionalCaseBodyPanel from './components/FunctionalCaseBodyPanel.vue'
import TmBackButton from './components/TmBackButton.vue'

const route = useRoute()
const router = useRouter()
const proStore = ProjectStore()
const uStore = UserStore()

const projectId = computed(() => proStore.projectInfo?.id)
const reviewId = computed(() => Number(route.params.id))
const canSubmit = computed(() => uStore.hasPermission('test_review:submit'))
const canManage = computed(() => uStore.hasPermission('test_review:manage'))
const canCancelReview = computed(() => {
  if (!review.value || !['pending', 'in_review'].includes(review.value.status)) return false
  const uid = Number(uStore.userInfo?.id)
  const reviewers = (review.value.reviewer_ids || []).map(Number)
  const isReviewer = uid && reviewers.includes(uid)
  const isCreator = review.value.create_by && uStore.userInfo?.username === review.value.create_by
  return isReviewer || isCreator || canManage.value
})

const loading = ref(false)
const saving = ref(false)
const review = ref(null)
const items = ref([])
const stats = ref(null)
const releaseOwnerId = ref(null)
const memberNames = ref(new Map())
const decideVisible = ref(false)
const decideItem = ref(null)
const decideForm = reactive({ decision: 'approved', comment: '', attachments: [], checklist: {} })
const itemFinalizeVisible = ref(false)
const finalizeItemRow = ref(null)
const itemFinalizeForm = reactive({ decision: 'approved', comment: '' })
const viewCaseVisible = ref(false)
const viewCaseRow = ref(null)

const toCasePayload = (row) => {
  if (!row) return null
  return {
    id: row.functional_case_id,
    title: row.case_title,
    module: row.case_module,
    precondition: row.case_precondition,
    steps: row.case_steps,
    source_requirement_id: row.source_requirement_id
  }
}

const decideCaseData = computed(() => toCasePayload(decideItem.value))
const viewCaseData = computed(() => toCasePayload(viewCaseRow.value))

const reviewAttachmentApi = {
  uploadAttachment: (...args) => testReviewApi.uploadAttachment(...args),
  attachmentUrl: (...args) => testReviewApi.attachmentUrl(...args)
}

const checklistItems = computed(() => review.value?.checklist_snapshot || [])

const canFinalizeAny = computed(() => {
  if (!review.value || review.value.status === 'cancelled') return false
  const uid = Number(uStore.userInfo?.id)
  if (uStore.userInfo?.is_superuser || canManage.value) return true
  return uid && releaseOwnerId.value && uid === Number(releaseOwnerId.value)
})

const canFinalizeItem = (row) => canFinalizeAny.value && !row?.owner_decision

const displayDecision = (row) => row?.owner_decision || row?.decision

const statusLabel = (s) =>
  ({
    pending: '待开始',
    in_review: '评审中',
    approved: '已通过',
    changes_requested: '需修改',
    cancelled: '已取消'
  }[s] || s)
const statusTagType = (s) =>
  ({
    pending: 'info',
    in_review: '',
    approved: 'success',
    changes_requested: 'warning',
    cancelled: 'info'
  }[s] || '')
const decisionLabel = (s) =>
  ({
    pending: '待评',
    approved: '通过',
    changes_requested: '需修改',
    rejected: '拒绝'
  }[s] || s)
const decisionTagType = (s) =>
  ({
    pending: 'info',
    approved: 'success',
    changes_requested: 'warning',
    rejected: 'danger'
  }[s] || 'info')

const memberLabel = (id) => formatMemberName(id, memberNames.value)

const pendingReviewers = (row) => {
  const required = (review.value?.reviewer_ids || []).map(Number)
  const done = new Set(
    (row.decisions_json || [])
      .filter((d) => d.reviewer_id != null && (d.decision || 'pending') !== 'pending')
      .map((d) => Number(d.reviewer_id))
  )
  return required.filter((rid) => !done.has(rid))
}

const initChecklistForm = (existing = {}) => {
  const out = {}
  for (const c of checklistItems.value) {
    const key = c.key
    if (!key) continue
    out[key] = !!existing[key]
  }
  decideForm.checklist = out
}

const load = async () => {
  if (!projectId.value || !reviewId.value) return
  loading.value = true
  try {
    memberNames.value = await loadMemberNameMap(projectId.value)
    const res = await testReviewApi.get(reviewId.value, projectId.value)
    const data = res.data?.data || {}
    review.value = data.review || null
    items.value = data.items || []
    stats.value = data.stats || null
    releaseOwnerId.value = data.release_owner_id ?? null
  } finally {
    loading.value = false
  }
}

const goBack = () => {
  if (review.value?.release_id) {
    router.push(`/test-releases/${review.value.release_id}?tab=reviews`)
  } else {
    router.push('/test-releases')
  }
}

const openDecide = (row) => {
  decideItem.value = row
  const uid = Number(uStore.userInfo?.id)
  const mine = (row.decisions_json || []).find((d) => Number(d.reviewer_id) === uid)
  decideForm.decision = mine?.decision || 'approved'
  decideForm.comment = mine?.comment || ''
  decideForm.attachments = Array.isArray(mine?.attachments) ? [...mine.attachments] : []
  initChecklistForm(row.checklist_result || {})
  decideVisible.value = true
}

const openViewCase = (row) => {
  viewCaseRow.value = row
  viewCaseVisible.value = true
}

const submitDecide = async () => {
  for (const c of checklistItems.value) {
    if (c.required && c.key && !decideForm.checklist[c.key]) {
      ElMessage.warning(`请完成必填检查项：${c.label || c.key}`)
      return
    }
  }
  saving.value = true
  try {
    const uid = uStore.userInfo?.id
    await testReviewApi.submitDecision(
      reviewId.value,
      decideItem.value.id,
      projectId.value,
      {
        decision: decideForm.decision,
        comment: decideForm.comment || null,
        reviewer_id: uid || undefined,
        attachments: decideForm.attachments || [],
        checklist_result: { ...decideForm.checklist }
      }
    )
    ElMessage.success('已提交')
    decideVisible.value = false
    await load()
  } finally {
    saving.value = false
  }
}

const openItemFinalize = (row) => {
  finalizeItemRow.value = row
  itemFinalizeForm.decision = row.owner_decision || row.decision || 'approved'
  itemFinalizeForm.comment = row.owner_comment || ''
  itemFinalizeVisible.value = true
}

const submitItemFinalize = async () => {
  if (!finalizeItemRow.value) return
  saving.value = true
  try {
    await testReviewApi.finalizeItem(
      reviewId.value,
      finalizeItemRow.value.id,
      projectId.value,
      {
        decision: itemFinalizeForm.decision,
        comment: itemFinalizeForm.comment || null
      }
    )
    ElMessage.success('已对该用例定版')
    itemFinalizeVisible.value = false
    await load()
  } finally {
    saving.value = false
  }
}

const cancelReview = async () => {
  await ElMessageBox.confirm('取消本批评审？', '确认', { type: 'warning' })
  await testReviewApi.cancel(reviewId.value, projectId.value)
  ElMessage.success('已取消')
  await load()
}

watch([projectId, reviewId], () => load())
onMounted(load)
</script>

<style scoped>
.tm-review-detail { padding: 16px; }
.header {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.header h2 { margin: 0; font-size: 20px; }
.actions { margin-left: auto; display: flex; gap: 8px; }
.stats-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-bottom: 12px;
  padding: 10px 12px;
  background: linear-gradient(180deg, #f7f9fc 0%, #fff 100%);
  border: 1px solid #e8edf5;
  border-radius: 10px;
}
.stat-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  background: #eef2f8;
  font-size: 13px;
  font-weight: 600;
}
.stat-chip .lab { font-weight: 400; color: #667085; }
.stat-chip.ok { background: #e8f8ef; color: #067647; }
.stat-chip.warn { background: #fff6e6; color: #b54708; }
.stat-chip.bad { background: #feeceb; color: #b42318; }
.reviewer-progress {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-left: 4px;
}
.rev-pill {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 999px;
  background: #f2f4f7;
  color: #475467;
}
.rev-pill.done {
  background: #e8f8ef;
  color: #067647;
}
.agg-hint { margin-bottom: 12px; }
.review-table { border-radius: 8px; overflow: hidden; }
.owner-tag { margin-left: 4px; }
.decision-list { display: flex; flex-direction: column; gap: 4px; }
.decision-row {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  flex-wrap: wrap;
}
.decision-row .who { color: #344054; min-width: 64px; }
.decision-row .cmt {
  color: #667085;
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.decision-row .att { color: #409eff; }
.decision-row.pending { opacity: 0.75; }
.decide-form :deep(.el-form-item) { margin-bottom: 16px; }
.case-preview {
  margin-bottom: 14px;
  padding-bottom: 14px;
  border-bottom: 1px solid #eaecf0;
}
.checklist-box {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
  background: #f9fafb;
  border-radius: 8px;
  border: 1px solid #eaecf0;
}
.check-row :deep(.el-checkbox) { height: auto; align-items: flex-start; }
.finalize-case {
  margin-bottom: 12px;
  font-size: 14px;
  color: #344054;
}
</style>
