<template>
  <div class="tm-defect-list" v-loading="loading">
    <div class="header">
      <h2>缺陷台账</h2>
      <div class="filters">
        <el-input
          v-model="filters.keyword"
          clearable
          placeholder="标题关键词"
          style="width: 180px"
          @keyup.enter="load"
        />
        <ReleaseSelect
          v-if="projectId"
          v-model="filters.release_id"
          :project-id="projectId"
          placeholder="全部版本"
          width="260px"
          @loaded="onReleasesLoaded"
        />
        <el-select v-model="filters.status" clearable placeholder="状态" style="width: 130px">
          <el-option v-for="s in statusOptions" :key="s" :label="defectStatusLabel(s)" :value="s" />
        </el-select>
        <el-select v-model="filters.severity" clearable placeholder="严重度" style="width: 120px">
          <el-option
            v-for="(label, key) in DEFECT_SEVERITY_LABELS"
            :key="key"
            :label="label"
            :value="key"
          />
        </el-select>
        <ProjectMemberSelect
          v-if="projectId"
          v-model="filters.assignee_id"
          :project-id="projectId"
          placeholder="负责人"
          width="160px"
        />
        <el-tag v-if="filters.case_id" closable type="info" @close="clearCaseFilter">
          用例 #{{ filters.case_id }}
        </el-tag>
        <el-button type="primary" @click="load">查询</el-button>
        <el-button v-if="canEdit" type="success" @click="openCreate">新建缺陷</el-button>
      </div>
    </div>

    <div class="stats-bar" v-if="stats.total != null">
      <span>共 {{ stats.total }} 条</span>
      <span v-for="(n, k) in stats.by_severity" :key="'s-' + k">{{ defectSeverityLabel(k) }} {{ n }}</span>
      <span v-for="(n, k) in stats.by_resolution" :key="'r-' + k">{{ defectResolutionLabel(k) }} {{ n }}</span>
    </div>

    <el-table :data="pagedRows" border stripe class="clickable" @row-click="onRowClick">
      <el-table-column prop="defect_key" label="编号" width="110" />
      <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
      <el-table-column prop="severity" label="严重度" width="100">
        <template #default="{ row }">
          <el-tag :type="DEFECT_SEVERITY_TAG_TYPE[row.severity] || 'info'" size="small" effect="light">
            {{ defectSeverityLabel(row.severity) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="priority" label="优先级" width="90">
        <template #default="{ row }">
          <el-tag :type="DEFECT_PRIORITY_TAG_TYPE[row.priority] || 'info'" size="small" effect="plain">
            {{ defectPriorityLabel(row.priority) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="110">
        <template #default="{ row }">
          <el-tag :type="DEFECT_STATUS_TAG_TYPE[row.status] || 'info'" size="small">
            {{ defectStatusLabel(row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="版本" min-width="150" show-overflow-tooltip>
        <template #default="{ row }">{{ releaseLabel(row.release_id) }}</template>
      </el-table-column>
      <el-table-column label="负责人" width="110" show-overflow-tooltip>
        <template #default="{ row }">{{ formatMemberName(row.assignee_id, memberNames) }}</template>
      </el-table-column>
      <el-table-column prop="create_time" label="创建" width="160">
        <template #default="{ row }">{{ formatTime(row.create_time) }}</template>
      </el-table-column>
      <el-table-column prop="update_time" label="更新" width="160">
        <template #default="{ row }">{{ formatTime(row.update_time) }}</template>
      </el-table-column>
      <el-table-column label="附件" width="70">
        <template #default="{ row }">
          {{ Array.isArray(row.attachments) && row.attachments.length ? row.attachments.length : '—' }}
        </template>
      </el-table-column>
      <el-table-column label="外链" width="70">
        <template #default="{ row }">
          <a
            v-if="safeExternalUrl(row.external_url)"
            :href="safeExternalUrl(row.external_url)"
            target="_blank"
            rel="noopener noreferrer"
            @click.stop
          >链接</a>
          <span v-else>—</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click.stop="openRow(row)">详情</el-button>
          <el-button
            v-if="canProcess(row) && quickAction(row)"
            link
            type="warning"
            @click.stop="openProcess(row)"
          >{{ quickAction(row).label }}</el-button>
          <el-button
            v-if="canEdit"
            link
            type="success"
            @click.stop="openRow(row, 'basic')"
          >编辑</el-button>
        </template>
      </el-table-column>
    </el-table>
    <div class="pager" v-if="rows.length">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="rows.length"
        :page-sizes="[20, 50, 100]"
        layout="total, sizes, prev, pager, next"
        background
      />
    </div>

    <DefectDetailDrawer
      v-if="projectId"
      ref="drawerRef"
      :project-id="projectId"
      :can-edit="canEdit"
      @saved="load"
      @deleted="load"
    />

    <el-dialog
      v-model="processVisible"
      :title="processTitle"
      width="520px"
      destroy-on-close
      append-to-body
    >
      <el-form label-width="100px" class="process-form">
        <el-form-item label="当前状态">
          <el-tag :type="DEFECT_STATUS_TAG_TYPE[processRow?.status] || 'info'">
            {{ defectStatusLabel(processRow?.status) }}
          </el-tag>
          <span class="arrow">→</span>
          <el-tag type="warning">{{ defectStatusLabel(processForm.to_status) }}</el-tag>
        </el-form-item>
        <el-form-item label="处理意见">
          <el-input
            v-model="processForm.comment"
            type="textarea"
            :rows="4"
            placeholder="说明本次处理内容、验证结果或转交原因"
          />
        </el-form-item>
        <el-form-item label="负责人">
          <ProjectMemberSelect
            v-if="projectId"
            v-model="processForm.assignee_id"
            :project-id="projectId"
            clearable
            placeholder="可改派负责人"
            width="100%"
          />
        </el-form-item>
        <el-form-item label="处理人">
          <ProjectMemberSelect
            v-if="projectId"
            v-model="processForm.handler_id"
            :project-id="projectId"
            clearable
            placeholder="当前处理人"
            width="100%"
          />
        </el-form-item>
        <el-form-item label="缺陷归属人">
          <ProjectMemberSelect
            v-if="projectId"
            v-model="processForm.attributor_id"
            :project-id="projectId"
            clearable
            placeholder="引入问题者（可选）"
            width="100%"
          />
        </el-form-item>
        <el-form-item v-if="processNeedsResolution" label="解决方案">
          <el-select v-model="processForm.resolution_type" clearable placeholder="选择方案" style="width: 100%">
            <el-option
              v-for="opt in resolutionOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item v-if="processNeedsResolution" label="处理说明">
          <el-input v-model="processForm.resolution_detail" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="processVisible = false">取消</el-button>
        <el-button type="primary" :loading="processSaving" @click="submitProcess">确认提交</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { testDefectApi } from '@/api/testManagement'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { UserStore } from '@/stores/module/UserStore'
import { formatMemberName, loadMemberNameMap } from '@/utils/projectMembers'
import { safeExternalUrl } from '@/utils/safeExternalUrl'
import {
  DEFECT_PRIORITY_TAG_TYPE,
  DEFECT_QUICK_TRANSITIONS,
  DEFECT_SEVERITY_LABELS,
  DEFECT_SEVERITY_TAG_TYPE,
  DEFECT_STATUS_TAG_TYPE,
  canUserProcessDefect,
  defectSeverityLabel,
  defectStatusLabel
} from '@/utils/defectDisplay'
import { defectPriorityLabel, defectResolutionLabel, DEFECT_RESOLUTION_OPTIONS } from '@/utils/tmDisplay'
import DefectDetailDrawer from './components/DefectDetailDrawer.vue'
import ProjectMemberSelect from './components/ProjectMemberSelect.vue'
import ReleaseSelect from './components/ReleaseSelect.vue'

const route = useRoute()
const proStore = ProjectStore()
const uStore = UserStore()

const projectId = computed(() => proStore.projectInfo?.id)
const canEdit = computed(() => uStore.hasPermission('test_defect:edit'))
const canView = computed(() => uStore.hasPermission('test_defect:view'))

const loading = ref(false)
const rows = ref([])
const stats = ref({ total: null, by_severity: {}, by_status: {}, by_resolution: {} })
const page = ref(1)
const pageSize = ref(20)
const drawerRef = ref(null)
const memberNames = ref(new Map())
const releaseMap = ref(new Map())
const processVisible = ref(false)
const processSaving = ref(false)
const processRow = ref(null)
const processForm = reactive({
  to_status: '',
  comment: '',
  assignee_id: null,
  handler_id: null,
  attributor_id: null,
  resolution_type: null,
  resolution_detail: ''
})
const filters = reactive({
  keyword: '',
  status: '',
  severity: '',
  assignee_id: null,
  release_id: route.query.release_id ? Number(route.query.release_id) : null,
  case_id: route.query.case_id ? Number(route.query.case_id) : null
})

const statusOptions = ['open', 'in_progress', 'resolved', 'verified', 'closed', 'rejected']

const clearCaseFilter = () => {
  filters.case_id = null
  load()
}

const pagedRows = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return rows.value.slice(start, start + pageSize.value)
})

const formatTime = (v) => (v ? String(v).replace('T', ' ').slice(0, 19) : '—')
const releaseLabel = (id) => {
  if (!id) return '—'
  return releaseMap.value.get(Number(id)) || `#${id}`
}
const quickAction = (row) => DEFECT_QUICK_TRANSITIONS[row.status] || null

const canProcess = (row) =>
  canUserProcessDefect(row, uStore.userInfo, {
    canView: canView.value,
    canEdit: canEdit.value
  })

const processTitle = computed(() => {
  const key = processRow.value?.defect_key || '缺陷'
  const action = quickAction(processRow.value)
  return action ? `${action.label} · ${key}` : `处理 · ${key}`
})

const resolutionOptions = DEFECT_RESOLUTION_OPTIONS
const processNeedsResolution = computed(() =>
  ['resolved', 'verified', 'closed'].includes(processForm.to_status)
)

const onReleasesLoaded = (list) => {
  const map = new Map()
  for (const r of list || []) {
    map.set(r.id, `${r.release_key || r.id} · ${r.name || ''}`)
  }
  releaseMap.value = map
}

const load = async () => {
  if (!projectId.value) return
  loading.value = true
  try {
    memberNames.value = await loadMemberNameMap(projectId.value)
    const res = await testDefectApi.list({
      project_id: projectId.value,
      keyword: filters.keyword || undefined,
      status: filters.status || undefined,
      severity: filters.severity || undefined,
      assignee_id: filters.assignee_id || undefined,
      release_id: filters.release_id || undefined,
      functional_case_id: filters.case_id || undefined
    })
    rows.value = res.data?.data || []
    page.value = 1
    try {
      const st = await testDefectApi.stats(projectId.value, {
        release_id: filters.release_id || undefined
      })
      stats.value = st.data?.data || { total: rows.value.length, by_severity: {}, by_status: {}, by_resolution: {} }
    } catch {
      stats.value = { total: rows.value.length, by_severity: {}, by_status: {}, by_resolution: {} }
    }
  } finally {
    loading.value = false
  }
}

const openCreate = () => {
  if (!projectId.value) {
    ElMessage.warning('请先选择项目')
    return
  }
  drawerRef.value?.openCreate({ release_id: filters.release_id || null })
}

const openRow = (row, tab) => {
  drawerRef.value?.open(row.id, tab ? { tab } : undefined)
}

const onRowClick = (row) => openRow(row)

const openProcess = (row) => {
  const action = quickAction(row)
  if (!action) return
  processRow.value = row
  processForm.to_status = action.to
  processForm.comment = ''
  processForm.assignee_id = row.assignee_id ?? null
  processForm.handler_id = row.handler_id ?? (uStore.userInfo?.id || null)
  processForm.attributor_id = row.attributor_id ?? null
  processForm.resolution_type = row.resolution_type ?? null
  processForm.resolution_detail = row.resolution_detail || ''
  processVisible.value = true
}

const submitProcess = async () => {
  if (!processRow.value) return
  processSaving.value = true
  try {
    await testDefectApi.transition(processRow.value.id, projectId.value, {
      to_status: processForm.to_status,
      comment: processForm.comment || null,
      assignee_id: processForm.assignee_id,
      handler_id: processForm.handler_id,
      attributor_id: processForm.attributor_id,
      resolution_type: processForm.resolution_type,
      resolution_detail: processForm.resolution_detail || null
    })
    ElMessage.success(`已更新为「${defectStatusLabel(processForm.to_status)}」`)
    processVisible.value = false
    await load()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '处理失败')
  } finally {
    processSaving.value = false
  }
}

const tryOpenQueryDefect = async () => {
  const id = route.query.defect_id ? Number(route.query.defect_id) : null
  if (id && projectId.value) {
    await drawerRef.value?.open(id)
  }
}

watch(projectId, () => load())
watch(
  () => route.query.release_id,
  (v) => {
    filters.release_id = v ? Number(v) : null
    load()
  }
)
watch(
  () => route.query.case_id,
  (v) => {
    filters.case_id = v ? Number(v) : null
    load()
  }
)
watch(
  () => route.query.defect_id,
  () => tryOpenQueryDefect()
)
onMounted(async () => {
  await load()
  await tryOpenQueryDefect()
})
</script>

<style scoped>
.tm-defect-list { padding: 16px; }
.header {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 12px;
}
.header h2 { margin: 0; font-size: 20px; }
.filters { display: flex; flex-wrap: wrap; gap: 8px; margin-left: auto; }
.stats-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 10px;
  font-size: 13px;
  color: #606266;
}
.pager { margin-top: 12px; display: flex; justify-content: flex-end; }
.clickable :deep(.el-table__row) { cursor: pointer; }
.process-form :deep(.el-form-item) { margin-bottom: 16px; }
.process-form .arrow { margin: 0 8px; color: #98a2b3; }
</style>
