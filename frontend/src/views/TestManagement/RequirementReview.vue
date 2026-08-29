<template>
  <div class="tm-req-review" :class="{ embedded }" v-loading="loading">
    <div v-if="!embedded" class="header">
      <div>
        <TmBackButton @click="goBack" />
        <h2>需求可测性评审</h2>
      </div>
      <div class="actions">
        <el-tag v-if="reviewStatus">评审状态：{{ statusLabel(reviewStatus) }}</el-tag>
        <el-button v-if="canManage" type="primary" @click="openCreate">发起评审</el-button>
        <el-button
          v-if="canEdit && ['rejected', 'changes_requested'].includes(reviewStatus)"
          @click="reopen"
        >重新提交</el-button>
      </div>
    </div>

    <div v-else class="pane-toolbar">
      <el-button v-if="canManage" type="primary" @click="openCreate">发起评审</el-button>
    </div>

    <el-alert
      v-if="reviewStatus && reviewStatus !== 'approved'"
      type="warning"
      :closable="false"
      show-icon
      title="需求未通过可测性评审时，将无法提取测试点或生成用例。"
      style="margin-bottom: 12px"
    />

    <el-table :data="reviews" border stripe>
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column label="需求" min-width="180" show-overflow-tooltip>
        <template #default="{ row }">{{ requirementName(row.requirement_id) }}</template>
      </el-table-column>
      <el-table-column prop="round" label="轮次" width="70" />
      <el-table-column prop="status" label="状态" width="120">
        <template #default="{ row }">{{ statusLabel(row.status) }}</template>
      </el-table-column>
      <el-table-column prop="reviewer_ids" label="评审人" min-width="160" show-overflow-tooltip>
        <template #default="{ row }">{{ formatMemberNames(row.reviewer_ids, memberNames) }}</template>
      </el-table-column>
      <el-table-column prop="summary" label="总结" min-width="180" show-overflow-tooltip />
      <el-table-column prop="create_time" label="创建" width="170">
        <template #default="{ row }">{{ formatTime(row.create_time) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="200" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openDetail(row)">详情</el-button>
          <el-button
            v-if="canManage && ['pending', 'in_review', 'changes_requested'].includes(row.status)"
            link
            type="success"
            @click="openComplete(row)"
          >定版</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="createVisible" title="发起需求评审" width="560px" destroy-on-close>
      <el-form label-width="100px">
        <el-form-item label="需求" required>
          <el-select
            v-model="createForm.requirement_ids"
            multiple
            filterable
            remote
            clearable
            collapse-tags
            collapse-tags-tooltip
            :remote-method="searchRequirements"
            :loading="reqLoading"
            placeholder="可多选，批量发起评审"
            style="width: 100%"
            @visible-change="(v) => v && loadRequirements()"
          >
            <el-option
              v-for="r in requirementOptions"
              :key="r.id"
              :label="requirementOptionLabel(r)"
              :value="r.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="评审人" required>
          <ProjectMemberSelect
            v-if="projectId"
            v-model="createForm.reviewer_ids"
            :project-id="projectId"
            multiple
            placeholder="可多选评审人"
            width="100%"
          />
        </el-form-item>
        <el-form-item label="评审说明">
          <el-input
            v-model="createForm.ai_assist_summary"
            type="textarea"
            :rows="3"
            placeholder="可选：补充背景、验收要点或粘贴摘要（非自动生成）"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitCreate">创建</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="detailVisible" size="520px" destroy-on-close class="req-review-drawer">
      <template #header>
        <div class="drawer-head">
          <div class="drawer-title">评审详情</div>
          <el-tag size="small" type="info" effect="plain">需求可测性评审</el-tag>
        </div>
      </template>
      <div v-if="detail" class="drawer-body">
        <div class="meta-card">
          <div class="meta-row">
            <span class="lab">状态</span>
            <el-tag size="small" :type="statusTagType(detail.review?.status)">
              {{ statusLabel(detail.review?.status) }}
            </el-tag>
          </div>
          <div class="meta-row">
            <span class="lab">总结</span>
            <span class="val">{{ detail.review?.summary || '—' }}</span>
          </div>
          <div class="meta-row" v-if="(detail.review?.reviewer_ids || []).length">
            <span class="lab">评审人</span>
            <span class="val">{{ formatMemberNames(detail.review.reviewer_ids, memberNames) }}</span>
          </div>
          <div class="meta-row" v-if="detail.stats">
            <span class="lab">结论进度</span>
            <span class="val">
              {{ detail.stats.done || 0 }}/{{ detail.stats.total || 0 }}
              <el-tag
                v-if="detail.stats.aggregate && detail.stats.aggregate !== 'pending'"
                size="small"
                :type="decisionTagType(detail.stats.aggregate)"
                style="margin-left: 6px"
              >聚合：{{ decisionLabel(detail.stats.aggregate) }}</el-tag>
            </span>
          </div>
        </div>

        <div v-if="detail.requirement_preview" class="req-body-section">
          <div class="section-title">需求正文</div>
          <div class="req-meta-mini">
            <span>{{ detail.requirement_preview.name || detail.requirement_preview.requirement_key }}</span>
            <el-tag v-if="detail.requirement_preview.parse_status" size="small" effect="plain">
              {{ detail.requirement_preview.parse_status }}
            </el-tag>
          </div>
          <div v-if="detail.requirement_preview.original_content" class="req-content">
            {{ detail.requirement_preview.original_content }}
          </div>
          <div v-else class="req-empty">暂无正文，请在需求工作台上传文档。</div>
          <router-link
            v-if="detail.requirement_preview.id"
            :to="`/ai-testing/requirements/${detail.requirement_preview.id}`"
            class="req-workbench-link"
          >
            打开需求工作台
          </router-link>
        </div>

        <div class="decision-section" v-if="(detail.stats?.reviewers || []).length">
          <div class="section-title">各人结论</div>
          <div
            v-for="r in detail.stats.reviewers"
            :key="r.reviewer_id"
            class="decision-row"
          >
            <span class="who">{{ memberName(r.reviewer_id) }}</span>
            <el-tag size="small" :type="decisionTagType(r.decision)">
              {{ decisionLabel(r.decision) }}
            </el-tag>
            <span v-if="r.comment" class="cmt" :title="r.comment">{{ r.comment }}</span>
          </div>
        </div>

        <el-alert
          type="info"
          :closable="false"
          show-icon
          class="agg-hint"
          title="多人评审：各评审人分别提交结论，任一人需修改/拒绝则聚合为需修改；全部通过后由管理员「完成」定版解锁用例设计。"
        />

        <div
          class="pane-toolbar"
          v-if="detail.review && !['approved', 'rejected'].includes(detail.review.status)"
        >
          <el-button
            v-if="canSubmitMine"
            type="warning"
            @click="openDecide"
          >提交我的结论</el-button>
          <el-button
            v-if="canEdit"
            type="primary"
            @click="openAddItem"
          >添加意见</el-button>
          <el-button
            v-if="canManage"
            type="success"
            @click="openComplete(detail.review)"
          >最终定版</el-button>
        </div>
        <el-timeline class="opinion-timeline">
          <el-timeline-item
            v-for="it in detail.items || []"
            :key="it.id"
            :type="severityTimelineType(it.severity)"
            placement="top"
          >
            <div class="opinion-card">
              <div class="opinion-head">
                <el-tag size="small" effect="plain">{{ categoryLabel(it.category) }}</el-tag>
                <el-tag size="small" :type="severityTagType(it.severity)">
                  {{ severityLabel(it.severity) }}
                </el-tag>
                <span class="opinion-by" v-if="it.create_by">{{ it.create_by }}</span>
              </div>
              <div class="opinion-body">{{ it.comment || '—' }}</div>
              <div v-if="it.suggested_fix" class="opinion-suggest">建议：{{ it.suggested_fix }}</div>
            </div>
          </el-timeline-item>
        </el-timeline>
        <el-empty v-if="!(detail.items || []).length" description="暂无意见" />
      </div>
    </el-drawer>

    <el-dialog v-model="itemVisible" title="添加评审意见" width="480px" destroy-on-close>
      <el-form label-width="90px">
        <el-form-item label="分类">
          <el-select v-model="itemForm.category" style="width: 220px">
            <el-option v-for="(lab, key) in categoryOptions" :key="key" :label="lab" :value="key" />
          </el-select>
        </el-form-item>
        <el-form-item label="严重度">
          <el-select v-model="itemForm.severity" style="width: 160px">
            <el-option label="高" value="high" />
            <el-option label="中" value="medium" />
            <el-option label="低" value="low" />
          </el-select>
        </el-form-item>
        <el-form-item label="意见">
          <el-input v-model="itemForm.comment" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="建议">
          <el-input v-model="itemForm.suggested_fix" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="itemVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitItem">提交</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="decideVisible" title="提交我的评审结论" width="440px" destroy-on-close>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        style="margin-bottom: 12px"
        title="仅更新你本人的结论，不会覆盖其他评审人。"
      />
      <el-form label-width="90px">
        <el-form-item label="结论" required>
          <el-select v-model="decideForm.decision" style="width: 200px">
            <el-option label="通过" value="approved" />
            <el-option label="需修改" value="changes_requested" />
            <el-option label="驳回" value="rejected" />
          </el-select>
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="decideForm.comment" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="decideVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitDecide">提交</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="completeVisible" title="最终定版（管理员）" width="440px" destroy-on-close>
      <el-alert
        type="warning"
        :closable="false"
        show-icon
        style="margin-bottom: 12px"
        title="定版后将更新需求可测性状态；通过后才可提取测试点/生成用例。"
      />
      <el-form label-width="90px">
        <el-form-item label="结论" required>
          <el-select v-model="completeForm.decision" style="width: 200px">
            <el-option label="通过" value="approved" />
            <el-option label="需修改" value="changes_requested" />
            <el-option label="驳回" value="rejected" />
          </el-select>
        </el-form-item>
        <el-form-item label="总结">
          <el-input v-model="completeForm.summary" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="completeVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitComplete">确认定版</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { aiRequirementApi } from '@/api/modules/ai.js'
import { testRequirementReviewApi, testReleaseApi } from '@/api/testManagement'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { UserStore } from '@/stores/module/UserStore'
import { formatMemberName, formatMemberNames, loadMemberNameMap } from '@/utils/projectMembers'
import {
  requirementParseStatusLabel,
  requirementReviewStatusLabel
} from '@/utils/tmDisplay'
import ProjectMemberSelect from './components/ProjectMemberSelect.vue'
import TmBackButton from './components/TmBackButton.vue'

const props = defineProps({
  embedded: { type: Boolean, default: false },
  releaseIdOverride: { type: Number, default: null },
  projectIdOverride: { type: Number, default: null }
})

const route = useRoute()
const router = useRouter()
const proStore = ProjectStore()
const uStore = UserStore()

const projectId = computed(() => props.projectIdOverride || proStore.projectInfo?.id)
const requirementId = computed(() =>
  route.query.requirement_id ? Number(route.query.requirement_id) : null
)
const releaseId = computed(() =>
  props.releaseIdOverride ?? (route.query.release_id ? Number(route.query.release_id) : null)
)
const canManage = computed(() => uStore.hasPermission('test_review:manage'))
const canSubmit = computed(() => uStore.hasPermission('test_review:submit') || canManage.value)
const canEdit = canSubmit

const loading = ref(false)
const saving = ref(false)
const reviews = ref([])
const reviewStatus = ref('')
const createVisible = ref(false)
const detailVisible = ref(false)
const itemVisible = ref(false)
const completeVisible = ref(false)
const decideVisible = ref(false)
const detail = ref(null)
const currentReview = ref(null)
const memberNames = ref(new Map())

const createForm = reactive({
  requirement_ids: [],
  reviewer_ids: [],
  ai_assist_summary: ''
})
const requirementOptions = ref([])
const reqLoading = ref(false)
const reqNameMap = ref(new Map())

const requirementName = (id) => {
  if (!id) return '—'
  return reqNameMap.value.get(Number(id)) || `需求 #${id}`
}
const memberName = (id) => formatMemberName(id, memberNames.value)
const itemForm = reactive({
  category: 'other',
  severity: 'medium',
  comment: '',
  suggested_fix: ''
})
const completeForm = reactive({
  decision: 'approved',
  summary: ''
})
const decideForm = reactive({
  decision: 'approved',
  comment: ''
})

const canSubmitMine = computed(() => {
  if (!canSubmit.value || !detail.value?.review) return false
  if (['approved', 'rejected'].includes(detail.value.review.status)) return false
  const uid = Number(uStore.userInfo?.id)
  const reviewers = (detail.value.review.reviewer_ids || []).map(Number)
  return uid && reviewers.includes(uid)
})

const categoryOptions = {
  scope_unclear: '范围不明确',
  acceptance_missing: '缺少验收标准',
  edge_case_gap: '边界场景遗漏',
  priority_issue: '优先级问题',
  testability_risk: '可测试性风险',
  other: '其他'
}

const statusLabel = (s) =>
  ({
    pending: '待评审',
    in_review: '评审中',
    approved: '已通过',
    changes_requested: '需修改',
    rejected: '已驳回'
  }[s] || s)
const statusTagType = (s) =>
  ({
    pending: 'info',
    in_review: '',
    approved: 'success',
    changes_requested: 'warning',
    rejected: 'danger'
  }[s] || 'info')
const categoryLabel = (c) => categoryOptions[c] || c
const severityLabel = (s) => ({ high: '高', medium: '中', low: '低' }[s] || s || '—')
const severityTagType = (s) => ({ high: 'danger', medium: 'warning', low: 'info' }[s] || 'info')
const severityTimelineType = (s) => ({ high: 'danger', medium: 'warning', low: 'primary' }[s] || 'info')
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
const formatTime = (v) => (v ? String(v).replace('T', ' ').slice(0, 19) : '—')

const load = async () => {
  if (!projectId.value) return
  loading.value = true
  try {
    memberNames.value = await loadMemberNameMap(projectId.value)
    await loadRequirements()
    const map = new Map()
    for (const r of requirementOptions.value) {
      map.set(r.id, r.name || `需求 #${r.id}`)
    }
    reqNameMap.value = map
    const listOpts = requirementId.value
      ? { requirementId: requirementId.value }
      : releaseId.value
        ? { releaseId: releaseId.value }
        : {}
    const res = await testRequirementReviewApi.list(projectId.value, listOpts)
    reviews.value = res.data?.data || []
    if (requirementId.value && reviews.value.length) {
      const latest = reviews.value[0]
      reviewStatus.value =
        latest.status === 'approved'
          ? 'approved'
          : latest.status === 'rejected'
            ? 'rejected'
            : latest.status === 'changes_requested'
              ? 'changes_requested'
              : latest.status === 'pending'
                ? 'pending'
                : 'in_review'
    } else if (requirementId.value) {
      reviewStatus.value = 'pending'
    } else {
      reviewStatus.value = ''
    }
  } finally {
    loading.value = false
  }
}

const goBack = () => {
  if (window.history.length > 1) {
    router.back()
    return
  }
  if (releaseId.value) {
    router.push(`/test-releases/${releaseId.value}?tab=req-reviews`)
    return
  }
  if (requirementId.value) {
    router.push({ path: '/ai-requirements', query: { requirement_id: String(requirementId.value) } })
    return
  }
  router.push('/test-releases')
}

const openCreate = async () => {
  createForm.requirement_ids = requirementId.value ? [requirementId.value] : []
  createForm.reviewer_ids = []
  createForm.ai_assist_summary = ''
  createVisible.value = true
  await loadRequirements()
}

const openCreateForRequirement = async (id) => {
  const rid = Number(id)
  if (!rid) return
  createForm.requirement_ids = [rid]
  createForm.reviewer_ids = []
  createForm.ai_assist_summary = ''
  createVisible.value = true
  await loadRequirements()
}

defineExpose({ openCreateForRequirement })

const requirementOptionLabel = (r) => {
  const parseSt = requirementParseStatusLabel(r.parse_status)
  const reviewSt = requirementReviewStatusLabel(r.review_status)
  const name = r.name || `需求 #${r.id}`
  const tags = [parseSt, reviewSt].filter(Boolean).join(' · ')
  return tags ? `#${r.id} · ${name}（${tags}）` : `#${r.id} · ${name}`
}

const activeReviewReqIds = computed(() => {
  const blocked = new Set()
  for (const rv of reviews.value) {
    if (['pending', 'in_review', 'changes_requested'].includes(rv.status)) {
      blocked.add(Number(rv.requirement_id))
    }
  }
  return blocked
})

const loadRequirements = async (keyword = '') => {
  if (!projectId.value) return
  reqLoading.value = true
  try {
    let list = []
    if (releaseId.value) {
      const res = await testReleaseApi.listRequirements(releaseId.value, projectId.value)
      list = (res.data?.data || [])
        .map((r) => {
          const key = String(r.requirement_key || '')
          const m = key.match(/^REQ-(\d+)$/i)
          const aiId = r.ai_requirement_id || (m ? Number(m[1]) : null)
          if (!aiId) return null
          return {
            id: Number(aiId),
            name: r.name || r.requirement_name || r.title || key,
            parse_status: r.ai_parse_status || r.parse_status || 'parsed',
            review_status: r.ai_review_status || r.review_status
          }
        })
        .filter(Boolean)
    } else if (requirementId.value) {
      const res = await aiRequirementApi.getList({
        project_id: projectId.value,
        page: 1,
        size: 200
      })
      const data = res.data?.data
      list = Array.isArray(data) ? data : data?.items || data?.list || []
      list = list.filter((r) => Number(r.id) === requirementId.value)
    } else {
      const res = await aiRequirementApi.getList({
        project_id: projectId.value,
        page: 1,
        size: 200
      })
      const data = res.data?.data
      list = Array.isArray(data) ? data : data?.items || data?.list || []
    }
    list = list.filter((r) => (r.parse_status || 'parsed') === 'parsed')
    list = list.filter((r) => !activeReviewReqIds.value.has(Number(r.id)))
    const kw = String(keyword || '').trim().toLowerCase()
    if (kw) {
      list = list.filter((r) => {
        const name = String(r.name || '').toLowerCase()
        const id = String(r.id || '')
        return name.includes(kw) || id.includes(kw)
      })
    }
    requirementOptions.value = list
  } catch {
    requirementOptions.value = []
  } finally {
    reqLoading.value = false
  }
}

const searchRequirements = (q) => {
  loadRequirements(q)
}

const submitCreate = async () => {
  const ids = (createForm.requirement_ids || []).map((x) => Number(x)).filter((x) => x > 0)
  if (!ids.length) {
    ElMessage.warning('请至少选择一条需求')
    return
  }
  if (!createForm.reviewer_ids?.length) {
    ElMessage.warning('请至少选择一位评审人')
    return
  }
  saving.value = true
  try {
    let ok = 0
    const failed = []
    for (const rid of ids) {
      try {
        await testRequirementReviewApi.create({
          project_id: projectId.value,
          requirement_id: rid,
          reviewer_ids: createForm.reviewer_ids,
          ai_assist_summary: createForm.ai_assist_summary || null
        })
        ok += 1
      } catch (e) {
        const msg = e?.response?.data?.detail || e?.message || '失败'
        failed.push(`#${rid}: ${msg}`)
      }
    }
    if (ok && !failed.length) {
      ElMessage.success(ok > 1 ? `已为 ${ok} 条需求发起评审` : '已发起评审')
    } else if (ok && failed.length) {
      ElMessage.warning(`成功 ${ok} 条，失败 ${failed.length} 条：${failed[0]}`)
    } else {
      ElMessage.error(failed[0] || '发起评审失败')
      return
    }
    createVisible.value = false
    await load()
  } finally {
    saving.value = false
  }
}

const openDetail = async (row) => {
  currentReview.value = row
  const res = await testRequirementReviewApi.get(row.id, projectId.value)
  detail.value = res.data?.data || null
  detailVisible.value = true
}

const openAddItem = () => {
  itemForm.category = 'other'
  itemForm.severity = 'medium'
  itemForm.comment = ''
  itemForm.suggested_fix = ''
  itemVisible.value = true
}

const openDecide = () => {
  const uid = Number(uStore.userInfo?.id)
  const mine = (detail.value?.review?.decisions_json || []).find(
    (d) => Number(d.reviewer_id) === uid
  )
  decideForm.decision = mine?.decision || 'approved'
  decideForm.comment = mine?.comment || ''
  decideVisible.value = true
}

const submitDecide = async () => {
  if (!currentReview.value) return
  saving.value = true
  try {
    await testRequirementReviewApi.submitDecision(currentReview.value.id, projectId.value, {
      decision: decideForm.decision,
      comment: decideForm.comment || null,
      reviewer_id: uStore.userInfo?.id || undefined
    })
    ElMessage.success('已提交结论')
    decideVisible.value = false
    await openDetail(currentReview.value)
    await load()
  } finally {
    saving.value = false
  }
}

const submitItem = async () => {
  if (!currentReview.value) return
  saving.value = true
  try {
    await testRequirementReviewApi.addItem(currentReview.value.id, projectId.value, {
      category: itemForm.category,
      severity: itemForm.severity,
      comment: itemForm.comment || null,
      suggested_fix: itemForm.suggested_fix || null
    })
    ElMessage.success('已添加')
    itemVisible.value = false
    await openDetail(currentReview.value)
  } finally {
    saving.value = false
  }
}

const openComplete = (row) => {
  currentReview.value = row
  const agg = row.aggregate_decision || detail.value?.stats?.aggregate
  completeForm.decision =
    agg && ['approved', 'changes_requested', 'rejected'].includes(agg) ? agg : 'approved'
  completeForm.summary = row.summary || ''
  completeVisible.value = true
}

const submitComplete = async () => {
  if (!currentReview.value) return
  saving.value = true
  try {
    await testRequirementReviewApi.complete(currentReview.value.id, projectId.value, {
      decision: completeForm.decision,
      summary: completeForm.summary || null
    })
    ElMessage.success('评审已完成')
    completeVisible.value = false
    await load()
  } finally {
    saving.value = false
  }
}

const reopen = async () => {
  if (!requirementId.value) {
    ElMessage.warning('请从需求工作台进入本页以重新提交')
    return
  }
  await testRequirementReviewApi.reopen(requirementId.value, projectId.value)
  ElMessage.success('已重新进入待评审')
  await load()
}

watch([projectId, requirementId, () => props.releaseIdOverride], () => load())
onMounted(load)
</script>

<style scoped>
.tm-req-review { padding: 16px; }
.tm-req-review.embedded { padding: 0; }
.pane-toolbar { margin-bottom: 12px; display: flex; justify-content: flex-end; gap: 8px; }
.header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.header h2 { display: inline; margin: 0 0 0 8px; font-size: 20px; vertical-align: middle; }
.actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.hint { color: #909399; font-size: 12px; margin-top: 4px; }
.drawer-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.drawer-title { font-size: 16px; font-weight: 600; }
.drawer-body { padding: 0 4px 12px; }
.meta-card {
  padding: 12px 14px;
  margin-bottom: 14px;
  border-radius: 12px;
  background: linear-gradient(180deg, #f7f9fc 0%, #fff 100%);
  border: 1px solid #e8edf5;
}
.req-body-section {
  margin-bottom: 16px;
  padding: 12px 14px;
  border: 1px solid #eaecf0;
  border-radius: 10px;
  background: #fafbfc;
}
.req-body-section .section-title {
  font-size: 13px;
  font-weight: 600;
  color: #344054;
  margin-bottom: 8px;
}
.req-meta-mini {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #475467;
  margin-bottom: 8px;
}
.req-content {
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 280px;
  overflow: auto;
  padding: 10px 12px;
  background: #fff;
  border-radius: 8px;
  border: 1px solid #eef2f6;
}
.req-empty {
  font-size: 13px;
  color: #909399;
}
.req-workbench-link {
  display: inline-block;
  margin-top: 8px;
  font-size: 13px;
  color: var(--el-color-primary);
  text-decoration: none;
}
.meta-row {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  margin-bottom: 8px;
}
.meta-row:last-child { margin-bottom: 0; }
.meta-row .lab {
  width: 48px;
  flex-shrink: 0;
  color: #667085;
  font-size: 13px;
  line-height: 24px;
}
.meta-row .val {
  flex: 1;
  color: #1f2937;
  font-size: 13px;
  line-height: 1.5;
  word-break: break-word;
}
.opinion-timeline { padding-left: 4px; }
.opinion-card {
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid #eef2f6;
  background: #fff;
  box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
}
.opinion-head {
  display: flex;
  gap: 6px;
  margin-bottom: 6px;
  flex-wrap: wrap;
  align-items: center;
}
.opinion-by {
  margin-left: auto;
  font-size: 12px;
  color: #98a2b3;
}
.opinion-body {
  font-size: 13px;
  color: #344054;
  line-height: 1.5;
  white-space: pre-wrap;
}
.opinion-suggest {
  margin-top: 6px;
  font-size: 12px;
  color: #667085;
  padding: 6px 8px;
  border-radius: 6px;
  background: #f8fafc;
}
.decision-section {
  margin-bottom: 12px;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid #eef2f6;
  background: #fafbfc;
}
.section-title {
  font-size: 13px;
  font-weight: 600;
  color: #344054;
  margin-bottom: 8px;
}
.decision-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  margin-bottom: 6px;
  flex-wrap: wrap;
}
.decision-row:last-child { margin-bottom: 0; }
.decision-row .who { min-width: 72px; color: #344054; }
.decision-row .cmt {
  color: #667085;
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.agg-hint { margin-bottom: 12px; }
.pane-toolbar { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
</style>
