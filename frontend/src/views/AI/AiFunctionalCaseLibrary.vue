<template>
  <PageCard>
    <template #title>
      <div class="page-head">
        <span>📚 功能测试用例库</span>
        <span class="sub">所属产品与所属模块分开维护；禅道 ID 可手工回填；勾选后可生成 Web 自动化用例</span>
      </div>
    </template>
    <template #main>
      <div class="toolbar">
        <el-input
          v-model="filters.keyword"
          placeholder="搜索标题"
          clearable
          style="width: 200px;"
          @keyup.enter="onSearch"
        />
        <el-select
          v-model="filters.product"
          filterable
          allow-create
          default-first-option
          clearable
          placeholder="所属产品"
          style="width: 140px;"
        >
          <el-option v-for="p in filterOptions.products" :key="'p-' + p" :label="p" :value="p" />
        </el-select>
        <el-select
          v-model="filters.module"
          filterable
          allow-create
          default-first-option
          clearable
          placeholder="所属模块"
          style="width: 140px;"
        >
          <el-option v-for="m in filterOptions.modules" :key="'m-' + m" :label="m" :value="m" />
        </el-select>
        <el-select
          v-model="filters.related_story"
          filterable
          allow-create
          default-first-option
          clearable
          placeholder="关联需求"
          style="width: 150px;"
        >
          <el-option
            v-for="r in filterOptions.related_stories"
            :key="'r-' + r"
            :label="r"
            :value="r"
          />
        </el-select>
        <el-input
          v-model="filters.zentao_case_id"
          placeholder="禅道ID搜索"
          clearable
          style="width: 118px;"
          @keyup.enter="onSearch"
        />
        <el-select
          v-model="filters.has_zentao_case_id"
          clearable
          placeholder="禅道ID筛选"
          style="width: 130px;"
          @change="onSearch"
        >
          <el-option label="有禅道ID" value="has" />
          <el-option label="无禅道ID" value="none" />
        </el-select>
        <el-select v-model="filters.priority" clearable placeholder="优先级" style="width: 100px;">
          <el-option label="1" value="1" /><el-option label="2" value="2" />
          <el-option label="3" value="3" /><el-option label="4" value="4" />
        </el-select>
        <el-select v-model="filters.source_type" clearable placeholder="来源" style="width: 150px;">
          <el-option v-for="(label, val) in SOURCE_LABELS" :key="val" :label="label" :value="val" />
        </el-select>
        <el-select
          v-model="filters.import_batch"
          clearable
          filterable
          placeholder="导入批次"
          style="width: 320px;"
          @change="onSearch"
        >
          <el-option
            v-for="b in importBatches"
            :key="b.import_batch"
            :label="batchOptionLabel(b)"
            :value="b.import_batch"
          />
        </el-select>
        <el-select v-model="filters.sort_by" placeholder="排序字段" style="width: 120px;">
          <el-option label="创建时间" value="create_time" />
          <el-option label="修改时间" value="update_time" />
          <el-option label="禅道ID" value="zentao_case_id" />
        </el-select>
        <el-select v-model="filters.sort_order" style="width: 88px;">
          <el-option label="降序" value="desc" />
          <el-option label="升序" value="asc" />
        </el-select>
        <el-button type="primary" @click="onSearch">查询</el-button>
        <TableColumnPicker
          :items="pickerItems"
          @toggle="setColumnVisible"
          @reorder="setPickerOrder"
          @reset="resetColumns"
        />
        <el-button v-if="canExecute" type="success" @click="openEdit()">新建</el-button>
        <el-upload
          v-if="canExecute"
          :show-file-list="false"
          accept=".xlsx,.xls"
          :http-request="handleImportXlsx"
        >
          <el-button type="warning">禅道 XLSX 导入</el-button>
        </el-upload>
        <el-button @click="handleExport">导出 XLSX</el-button>
        <el-checkbox v-if="canExecute" v-model="dupStrictMode" class="dup-strict-check">
          严格模式（含步骤）
        </el-checkbox>
        <el-button v-if="canExecute" type="info" @click="runDuplicateCheck">重复检验</el-button>
        <el-button
          v-if="canExecute && filters.import_batch"
          type="danger"
          plain
          @click="rollbackImportBatch"
        >回滚本批</el-button>
        <el-button
          v-if="canImportUi && selectedIds.length"
          type="primary"
          @click="openToUiDialog"
        >AI 生成 UI ({{ selectedIds.length }})</el-button>
        <el-button
          v-if="canImportApp && selectedIds.length"
          type="primary"
          plain
          @click="openToAppDialog"
        >AI 生成 App ({{ selectedIds.length }})</el-button>
        <el-button
          v-if="canImportUi && selectedIds.length === 1"
          type="success"
          @click="openRecordDialog"
        >录制生成 UI</el-button>
        <el-button
          v-if="canExecute && selectedIds.length"
          type="danger"
          @click="handleBatchDelete"
        >删除选中 ({{ selectedIds.length }})</el-button>
      </div>

      <el-table
        v-loading="loading"
        :key="listTableKey"
        :data="caseList"
        border
        stripe
        @selection-change="onSelect"
      >
        <el-table-column type="selection" width="45" fixed="left" />
        <template v-for="col in activeColumns" :key="col.key">
          <el-table-column
            v-if="col.key === 'id'"
            prop="id"
            label="ID"
            :width="col.width"
            fixed="left"
          />
          <el-table-column
            v-else-if="col.key === 'zentao_case_id_display'"
            label="禅道ID"
            :width="col.width"
          >
            <template #default="{ row }">{{ row.zentao_case_id_display || '—' }}</template>
          </el-table-column>
          <el-table-column
            v-else-if="col.key === 'product'"
            prop="product"
            label="所属产品"
            :width="col.width"
            show-overflow-tooltip
          />
          <el-table-column
            v-else-if="col.key === 'module'"
            prop="module"
            label="所属模块"
            :width="col.width"
            show-overflow-tooltip
          />
          <el-table-column
            v-else-if="col.key === 'related_story'"
            prop="related_story"
            label="关联需求"
            :min-width="col.minWidth || 140"
            show-overflow-tooltip
          />
          <el-table-column
            v-else-if="col.key === 'title'"
            prop="title"
            label="用例标题"
            :min-width="col.minWidth || 220"
            show-overflow-tooltip
          />
          <el-table-column
            v-else-if="col.key === 'precondition'"
            prop="precondition"
            label="前置条件"
            :min-width="col.minWidth || 140"
            show-overflow-tooltip
          />
          <el-table-column
            v-else-if="col.key === 'steps_text'"
            label="步骤"
            :min-width="col.minWidth || 200"
          >
            <template #default="{ row }">
              <div class="steps-cell" :title="formatStepsText(row.steps)">
                {{ formatStepsText(row.steps) || '—' }}
              </div>
            </template>
          </el-table-column>
          <el-table-column
            v-else-if="col.key === 'expects_text'"
            label="预期"
            :min-width="col.minWidth || 200"
          >
            <template #default="{ row }">
              <div class="steps-cell" :title="formatExpectsText(row.steps)">
                {{ formatExpectsText(row.steps) || '—' }}
              </div>
            </template>
          </el-table-column>
          <el-table-column
            v-else-if="col.key === 'priority'"
            prop="priority"
            label="优先级"
            :width="col.width"
            align="center"
          />
          <el-table-column
            v-else-if="col.key === 'type'"
            prop="type"
            label="用例类型"
            :width="col.width"
          />
          <el-table-column
            v-else-if="col.key === 'stage'"
            prop="stage"
            label="适用阶段"
            :width="col.width"
            show-overflow-tooltip
          />
          <el-table-column
            v-else-if="col.key === 'source_type'"
            label="来源"
            :width="col.width"
          >
            <template #default="{ row }">
              <span>{{ SOURCE_LABELS[row.source_type] || row.source_type }}</span>
              <el-button
                v-if="row.source_requirement_id"
                link
                type="primary"
                size="small"
                style="margin-left: 4px;"
                @click="goSourceRequirement(row)"
              >需求</el-button>
            </template>
          </el-table-column>
          <el-table-column
            v-else-if="col.key === 'ui_import_status'"
            label="Web 自动化"
            :width="col.width"
            align="center"
          >
            <template #default="{ row }">
              <el-tag :type="uiTagType(row.ui_import_status)" size="small">
                {{ UI_STATUS_LABELS[row.ui_import_status] || '未生成' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column
            v-else-if="col.key === 'app_import_status'"
            label="App自动化"
            :width="col.width"
            align="center"
          >
            <template #default="{ row }">
              <el-tag :type="uiTagType(row.app_import_status)" size="small">
                {{ UI_STATUS_LABELS[row.app_import_status] || '未生成' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column
            v-else-if="col.key === 'create_by'"
            prop="create_by"
            label="创建人"
            :width="col.width"
          />
          <el-table-column
            v-else-if="col.key === 'update_by'"
            label="修改人"
            :width="col.width"
          >
            <template #default="{ row }">{{ row.update_by || '—' }}</template>
          </el-table-column>
          <el-table-column
            v-else-if="col.key === 'create_time'"
            prop="create_time"
            label="创建时间"
            :width="col.width"
          />
          <el-table-column
            v-else-if="col.key === 'update_time'"
            prop="update_time"
            label="更新时间"
            :width="col.width"
          />
        </template>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button
              v-if="row.ui_case_id"
              link
              type="success"
              @click="goUiCase(row.ui_case_id)"
            >UI 用例</el-button>
            <el-button
              v-if="row.app_case_id"
              link
              type="success"
              @click="goAppCase(row.app_case_id)"
            >App 用例</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        layout="total, prev, pager, next, sizes"
        :page-sizes="[20, 50, 100]"
        style="margin-top: 12px; justify-content: flex-end;"
        @current-change="loadList"
        @size-change="loadList"
      />

      <el-dialog
        v-model="editVisible"
        :title="editDialogTitle"
        width="820px"
        destroy-on-close
        top="5vh"
        @closed="editForm = null"
      >
        <el-form v-if="editForm" label-width="110px" class="edit-form">
          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item label="所属产品">
                <el-input v-model="editForm.product" placeholder="禅道「所属产品」" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="所属模块">
                <el-input v-model="editForm.module" placeholder="功能模块路径，与产品区分" />
              </el-form-item>
            </el-col>
            <el-col :span="24">
              <el-form-item label="关联需求">
                <el-input v-model="editForm.related_story" placeholder="相关研发需求" />
              </el-form-item>
            </el-col>
            <el-col :span="24">
              <el-form-item label="用例标题" required>
                <el-input v-model="editForm.title" type="textarea" :rows="2" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="禅道ID">
                <el-input
                  v-model="editForm.zentao_case_id"
                  placeholder="禅道用例编号（导入禅道后可回填）"
                  clearable
                />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="优先级">
                <el-select v-model="editForm.priority" style="width: 100%;">
                  <el-option label="1-高" value="1" /><el-option label="2-中" value="2" />
                  <el-option label="3-低" value="3" /><el-option label="4-建议" value="4" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="用例类型">
                <el-select v-model="editForm.type" style="width: 100%;">
                  <el-option v-for="t in ZENTAO_CASE_TYPES" :key="t" :label="t" :value="t" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="适用阶段"><el-input v-model="editForm.stage" /></el-form-item>
            </el-col>
            <el-col :span="24">
              <el-form-item label="前置条件">
                <el-input v-model="editForm.precondition" type="textarea" :rows="2" />
              </el-form-item>
            </el-col>
            <el-col :span="24">
              <el-form-item label="关键词"><el-input v-model="editForm.keywords" /></el-form-item>
            </el-col>
          </el-row>
          <el-form-item label="步骤">
            <div v-for="(st, idx) in editForm.steps" :key="idx" class="step-row">
              <el-input v-model="st.step" placeholder="步骤" type="textarea" :rows="1" />
              <el-input v-model="st.expect" placeholder="预期" type="textarea" :rows="1" />
              <el-button link type="danger" @click="editForm.steps.splice(idx, 1)">删</el-button>
            </div>
            <el-button size="small" @click="editForm.steps.push({ step: '', expect: '' })">+ 步骤</el-button>
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="editVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="saveEdit">保存</el-button>
        </template>
      </el-dialog>

      <el-drawer v-model="dupVisible" title="重复检验结果" size="920px" class="dup-drawer">
        <div v-if="!dupGroups.length" class="dup-empty">
          未发现重复（{{ dupStrictMode ? '标题 + 模块 + 步骤摘要' : '用例标题 + 所属模块' }} 相同）
        </div>
        <el-collapse v-else accordion class="dup-collapse">
          <el-collapse-item v-for="(g, i) in dupGroups" :key="i" :name="String(i)">
            <template #title>
              <div class="dup-group-title">
                <div class="dup-group-line1">
                  <el-tag size="small" type="danger">{{ g.cases.length }} 条重复</el-tag>
                  <span class="dup-module">模块：{{ g.key.module || '（空）' }}</span>
                </div>
                <div class="dup-group-line2" :title="g.key.title">{{ g.key.title }}</div>
              </div>
            </template>
            <el-table
              :data="g.cases"
              size="small"
              border
              max-height="360"
              @selection-change="rows => onDupGroupSelect(g, rows)"
            >
              <el-table-column type="selection" width="42" fixed="left" />
              <el-table-column prop="id" label="ID" width="64" fixed="left" />
              <el-table-column label="禅道ID" width="88">
                <template #default="{ row }">{{ row.zentao_case_id_display || '—' }}</template>
              </el-table-column>
              <el-table-column prop="product" label="所属产品" width="100" show-overflow-tooltip />
              <el-table-column prop="module" label="所属模块" width="120" show-overflow-tooltip />
              <el-table-column prop="title" label="用例标题" min-width="200" show-overflow-tooltip />
              <el-table-column prop="related_story" label="关联需求" width="120" show-overflow-tooltip />
              <el-table-column label="来源" width="96">
                <template #default="{ row }">
              <span>{{ SOURCE_LABELS[row.source_type] || row.source_type }}</span>
              <el-button
                v-if="row.source_requirement_id"
                link
                type="primary"
                size="small"
                style="margin-left: 4px;"
                @click="goSourceRequirement(row)"
              >需求</el-button>
            </template>
              </el-table-column>
              <el-table-column prop="create_by" label="创建人" width="88" />
              <el-table-column prop="create_time" label="创建时间" width="158" />
            </el-table>
          </el-collapse-item>
        </el-collapse>
        <div v-if="dupGroups.length" class="dup-actions">
          <el-button type="danger" plain @click="deleteDupKeepOnePerGroup">
            每组留一条并删除 ({{ dupKeepOneDeleteCount }})
          </el-button>
          <el-button type="danger" :disabled="!dupSelectedIds.length" @click="deleteDupSelected">
            删除已选重复项 ({{ dupSelectedIds.length }})
          </el-button>
        </div>
      </el-drawer>

      <FunctionalCaseToUiDialog
        v-if="projectId()"
        v-model="toUiVisible"
        :case-ids="selectedIds"
        :cases="caseList"
        :project-id="projectId()"
        @done="onToUiDone"
      />
      <FunctionalCaseToAppDialog
        v-if="projectId()"
        v-model="toAppVisible"
        :case-ids="selectedIds"
        :cases="caseList"
        :project-id="projectId()"
        @done="onToAppDone"
      />
      <FunctionalCaseRecordDialog
        v-if="projectId()"
        v-model="recordVisible"
        :functional-case="recordCase"
        :project-id="projectId()"
        @done="onRecordDone"
      />
    </template>
  </PageCard>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import PageCard from '@/components/PageCard.vue'
import TableColumnPicker from '@/components/TableColumnPicker.vue'
import FunctionalCaseToUiDialog from '@/views/AI/components/FunctionalCaseToUiDialog.vue'
import FunctionalCaseToAppDialog from '@/views/AI/components/FunctionalCaseToAppDialog.vue'
import FunctionalCaseRecordDialog from '@/views/AI/components/FunctionalCaseRecordDialog.vue'
import { aiFunctionalCaseApi } from '@/api/modules/ai.js'
import { ProjectStore } from '@/stores/module/ProjectStore.js'
import { UserStore } from '@/stores/module/UserStore.js'
import { useTableColumns } from '@/composables/useTableColumns.js'
import { formatStepsText, formatExpectsText } from '@/utils/formatCaseSteps.js'
import { ZENTAO_CASE_TYPES } from '@/constants/zentaoCaseTypes.js'

const {
  activeColumns,
  pickerItems,
  tableRenderKey,
  setColumnVisible,
  setPickerOrder,
  resetColumns
} = useTableColumns('ai.functional_cases')

const SOURCE_LABELS = {
  requirement_copy: '需求复制',
  test_analysis_copy: '测试分析',
  zentao_xlsx: '禅道导入',
  manual: '手工'
}
const UI_STATUS_LABELS = {
  none: '未生成',
  generating: '生成中',
  generated: '已生成',
  imported: '已导入',
  failed: '失败'
}

const proStore = ProjectStore()
const uStore = UserStore()
const router = useRouter()
const canExecute = computed(() => uStore.hasPermission('ai_test:execute'))
const canImportUi = computed(
  () => uStore.hasPermission('ai_test:execute') && uStore.hasPermission('ui_case:edit')
)
const canImportApp = computed(
  () => uStore.hasPermission('ai_test:execute') && uStore.hasPermission('app_case:edit')
)

const toUiVisible = ref(false)
const toAppVisible = ref(false)
const recordVisible = ref(false)
const recordCase = ref(null)

const loading = ref(false)
const caseList = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const selectedIds = ref([])

const filters = reactive({
  keyword: '',
  product: '',
  module: '',
  related_story: '',
  zentao_case_id: '',
  has_zentao_case_id: '',
  priority: '',
  source_type: '',
  import_batch: '',
  sort_by: 'create_time',
  sort_order: 'desc'
})

const importBatches = ref([])
const filterOptions = reactive({
  products: [],
  modules: [],
  related_stories: []
})
const dupStrictMode = ref(false)

const listTableKey = computed(
  () => `${tableRenderKey.value}-${filters.sort_by}-${filters.sort_order}-${page.value}-${total.value}`
)

const projectId = () => {
  const id = proStore.projectInfo?.id
  return id != null && id !== '' ? id : null
}

const buildListQueryParams = (extra = {}) => ({
  project_id: projectId(),
  page: page.value,
  size: pageSize.value,
  keyword: filters.keyword || undefined,
  product: filters.product || undefined,
  module: filters.module || undefined,
  related_story: filters.related_story || undefined,
  zentao_case_id: filters.zentao_case_id || undefined,
  has_zentao_case_id: filters.has_zentao_case_id || undefined,
  priority: filters.priority || undefined,
  source_type: filters.source_type || undefined,
  import_batch: filters.import_batch || undefined,
  sort_by: filters.sort_by || undefined,
  sort_order: filters.sort_order || undefined,
  ...extra
})

const buildExportFilterParams = () => {
  const { project_id, page: _p, size: _s, ...rest } = buildListQueryParams()
  return rest
}

const onSearch = () => {
  page.value = 1
  loadList()
}

const editVisible = ref(false)
const editForm = ref(null)
const editDialogTitle = computed(() => (editForm.value?.id ? '编辑用例' : '新建用例'))
const saving = ref(false)

const dupVisible = ref(false)
const dupGroups = ref([])
const dupSelectedIds = ref([])
const dupSelectSet = ref(new Set())

const uiTagType = (s) => {
  if (s === 'imported') return 'success'
  if (s === 'failed') return 'danger'
  if (s === 'generated') return 'warning'
  return 'info'
}

const batchOptionLabel = (b) => {
  const name = b.source_file_name || '导入批次'
  const shortId = (b.import_batch || '').slice(0, 8)
  let timeStr = ''
  if (b.latest_create_time) {
    const d = new Date(b.latest_create_time)
    if (!Number.isNaN(d.getTime())) {
      timeStr = d.toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false
      })
    }
  }
  const parts = [name, `${b.count}条`]
  if (timeStr) parts.push(timeStr)
  parts.push(shortId)
  return parts.join(' · ')
}

const loadImportBatches = async () => {
  if (!projectId()) return
  try {
    const res = await aiFunctionalCaseApi.getImportBatches(projectId())
    if (res.data?.code === 200) {
      importBatches.value = res.data.data?.batches || []
    }
  } catch (_) {
    importBatches.value = []
  }
}

const loadFilterOptions = async () => {
  if (!projectId()) return
  try {
    const res = await aiFunctionalCaseApi.getFilterOptions(projectId())
    if (res.data?.code === 200) {
      const data = res.data.data || {}
      filterOptions.products = data.products || []
      filterOptions.modules = data.modules || []
      filterOptions.related_stories = data.related_stories || []
    }
  } catch (_) {
    filterOptions.products = []
    filterOptions.modules = []
    filterOptions.related_stories = []
  }
}

const loadList = async () => {
  if (!projectId()) {
    ElMessage.warning('请先选择项目')
    return
  }
  loading.value = true
  try {
    const res = await aiFunctionalCaseApi.getList(buildListQueryParams())
    if (res.data?.code === 200) {
      caseList.value = res.data.data?.list || []
      total.value = res.data.data?.total || 0
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载失败')
  } finally {
    loading.value = false
  }
}

const onSelect = (rows) => {
  selectedIds.value = rows.map(r => r.id)
}

const openEdit = (row) => {
  if (row) {
    editForm.value = {
      id: row.id,
      product: row.product || '',
      module: row.module || '',
      related_story: row.related_story || '',
      title: row.title,
      zentao_case_id: row.zentao_case_id || '',
      source_type: row.source_type,
      precondition: row.precondition || '',
      priority: row.priority,
      type: row.type || '功能测试',
      stage: row.stage || '系统测试阶段',
      keywords: row.keywords || '',
      status: row.status || 'confirmed',
      steps: (row.steps || []).map(s => ({ step: s.step || '', expect: s.expect || '' }))
    }
  } else {
    editForm.value = {
      id: null,
      product: '',
      module: '',
      related_story: '',
      title: '',
      zentao_case_id: '',
      source_type: 'manual',
      precondition: '',
      priority: '2',
      type: '功能测试',
      stage: '系统测试阶段',
      keywords: '',
      status: 'confirmed',
      steps: [{ step: '', expect: '' }]
    }
  }
  editVisible.value = true
}

const saveEdit = async () => {
  if (!editForm.value.title?.trim()) {
    ElMessage.warning('请填写用例标题')
    return
  }
  saving.value = true
  try {
    const payload = { ...editForm.value }
    delete payload.id
    delete payload.source_type
    let res
    if (editForm.value.id) {
      res = await aiFunctionalCaseApi.update(editForm.value.id, payload, projectId())
    } else {
      res = await aiFunctionalCaseApi.create(payload, projectId())
    }
    if (res.data?.code === 200) {
      ElMessage.success('保存成功')
      editVisible.value = false
      loadList()
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

const handleImportXlsx = async ({ file }) => {
  try {
    const res = await aiFunctionalCaseApi.importZentao(file, projectId())
    if (res.data?.code === 200) {
      const d = res.data.data || {}
      ElMessage.success(res.data.message || `导入 ${d.imported_count} 条`)
      if (d.warnings?.length) {
        ElMessage.warning(`有 ${d.warnings.length} 条提示，可点「重复检验」清理`)
      }
      loadImportBatches()
      loadFilterOptions()
      loadList()
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '导入失败')
  }
}

const handleExport = async () => {
  const sortParams = {
    sort_by: filters.sort_by || undefined,
    sort_order: filters.sort_order || undefined
  }
  const exportOptions = selectedIds.value.length
    ? { ids: selectedIds.value, filters: sortParams }
    : { filters: buildExportFilterParams() }
  const url = aiFunctionalCaseApi.exportXlsxUrl(projectId(), exportOptions)
  try {
    const res = await fetch(url, { headers: { Authorization: 'Bearer ' + uStore.token } })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || '导出失败')
    }
    const blob = await res.blob()
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = 'functional_cases_zentao.xlsx'
    a.click()
    URL.revokeObjectURL(a.href)
    ElMessage.success('导出成功')
  } catch (e) {
    ElMessage.error(e.message || '导出失败')
  }
}

const runDuplicateCheck = async () => {
  try {
    const res = await aiFunctionalCaseApi.duplicateCheck(
      {
        module: filters.module || undefined,
        source_type: filters.source_type || undefined,
        import_batch: filters.import_batch || undefined,
        strict_mode: dupStrictMode.value
      },
      projectId()
    )
    if (res.data?.code === 200) {
      dupGroups.value = res.data.data?.groups || []
      dupSelectedIds.value = []
      dupSelectSet.value = new Set()
      dupVisible.value = true
      if (!dupGroups.value.length) ElMessage.success('未发现重复用例')
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '检验失败')
  }
}

const onDupGroupSelect = (g, rows) => {
  const groupIds = g.cases.map(c => c.id)
  groupIds.forEach(id => dupSelectSet.value.delete(id))
  rows.forEach(r => dupSelectSet.value.add(r.id))
  dupSelectedIds.value = [...dupSelectSet.value]
}

/** 每组保留 ID 最小的一条，其余为待删重复项 */
const collectDupIdsKeepOnePerGroup = () => {
  const toDelete = []
  for (const g of dupGroups.value) {
    const cases = g.cases || []
    if (cases.length < 2) continue
    const sorted = [...cases].sort((a, b) => a.id - b.id)
    for (let i = 1; i < sorted.length; i += 1) {
      toDelete.push(sorted[i].id)
    }
  }
  return toDelete
}

const dupKeepOneDeleteCount = computed(() => collectDupIdsKeepOnePerGroup().length)

const deleteDupKeepOnePerGroup = async () => {
  const ids = collectDupIdsKeepOnePerGroup()
  if (!ids.length) {
    ElMessage.info('没有可删除的重复项')
    return
  }
  try {
    await ElMessageBox.confirm(
      `共 ${dupGroups.value.length} 组重复，每组保留 ID 最小的一条，删除其余 ${ids.length} 条。此操作不可恢复，确定继续？`,
      '每组留一条',
      { type: 'warning' }
    )
    const res = await aiFunctionalCaseApi.batchDelete(ids, projectId())
    if (res.data?.code === 200) {
      ElMessage.success(`已删除 ${ids.length} 条重复用例`)
      dupSelectedIds.value = []
      dupSelectSet.value = new Set()
      await runDuplicateCheck()
      loadList()
    }
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

const deleteDupSelected = async () => {
  await ElMessageBox.confirm(`确定删除选中的 ${dupSelectedIds.value.length} 条？`, '提示', { type: 'warning' })
  try {
    const res = await aiFunctionalCaseApi.batchDelete(dupSelectedIds.value, projectId())
    if (res.data?.code === 200) {
      ElMessage.success('删除成功')
      dupSelectedIds.value = []
      dupSelectSet.value = new Set()
      await runDuplicateCheck()
      loadList()
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

const rollbackImportBatch = async () => {
  const batch = filters.import_batch
  if (!batch) return
  const meta = importBatches.value.find(b => b.import_batch === batch)
  const label = meta ? batchOptionLabel(meta) : batch.slice(0, 8)
  await ElMessageBox.confirm(
    `确定回滚删除批次「${label}」下的全部用例？此操作不可恢复。`,
    '按批回滚',
    { type: 'warning' }
  )
  try {
    const res = await aiFunctionalCaseApi.deleteByImportBatch(batch, projectId())
    if (res.data?.code === 200) {
      ElMessage.success(res.data.message || '回滚成功')
      filters.import_batch = ''
      loadImportBatches()
      loadFilterOptions()
      loadList()
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '回滚失败')
  }
}

const handleBatchDelete = async () => {
  await ElMessageBox.confirm(`确定删除 ${selectedIds.value.length} 条？`, '提示', { type: 'warning' })
  try {
    const res = await aiFunctionalCaseApi.batchDelete(selectedIds.value, projectId())
    if (res.data?.code === 200) {
      ElMessage.success('删除成功')
      selectedIds.value = []
      loadList()
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

const goUiCase = (id) => {
  router.push({ path: `/case/edit/${id}` })
}

const goAppCase = (id) => {
  router.push({ name: 'appCaseEdit', params: { id } })
}

const goSourceRequirement = (row) => {
  if (!row.source_requirement_id) return
  router.push({
    name: 'aiTestingWorkspace',
    params: { reqId: String(row.source_requirement_id) },
    query: { tab: 'cases' }
  })
}

const openRecordDialog = () => {
  if (!projectId()) {
    ElMessage.warning('请先选择项目')
    return
  }
  if (selectedIds.value.length !== 1) {
    ElMessage.warning('录制生成每次仅支持 1 条功能用例')
    return
  }
  const fc = caseList.value.find(c => c.id === selectedIds.value[0])
  if (!fc) {
    ElMessage.warning('未找到选中的功能用例')
    return
  }
  recordCase.value = fc
  recordVisible.value = true
}

const onRecordDone = () => {
  selectedIds.value = []
  recordCase.value = null
  loadList()
}

const openToUiDialog = () => {
  if (!projectId()) {
    ElMessage.warning('请先选择项目')
    return
  }
  if (!selectedIds.value.length) {
    ElMessage.warning('请先勾选功能用例')
    return
  }
  if (selectedIds.value.length > 10) {
    ElMessage.warning('单次最多 10 条，请减少勾选')
    return
  }
  toUiVisible.value = true
}

const onToUiDone = () => {
  selectedIds.value = []
  loadList()
}

const openToAppDialog = () => {
  if (!projectId()) {
    ElMessage.warning('请先选择项目')
    return
  }
  if (!selectedIds.value.length) {
    ElMessage.warning('请先勾选功能用例')
    return
  }
  if (selectedIds.value.length > 10) {
    ElMessage.warning('单次最多 10 条，请减少勾选')
    return
  }
  toAppVisible.value = true
}

const onToAppDone = () => {
  selectedIds.value = []
  loadList()
}

onMounted(() => {
  if (!projectId()) {
    ElMessage.warning('请先在顶部选择项目')
    return
  }
  loadImportBatches()
  loadFilterOptions()
  loadList()
})

watch(
  () => proStore.projectInfo?.id,
  (id, prev) => {
    if (id && id !== prev) {
      loadImportBatches()
      loadFilterOptions()
      page.value = 1
      loadList()
    }
  }
)

watch(
  () => [filters.sort_by, filters.sort_order],
  () => {
    page.value = 1
    loadList()
  }
)
</script>

<style scoped lang="scss">
.page-head {
  display: flex;
  flex-direction: column;
  gap: 4px;
  .sub { font-size: 12px; color: var(--el-text-color-secondary); font-weight: normal; }
}
.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
  align-items: center;
}
.dup-strict-check {
  margin-left: 2px;
}
.steps-cell {
  white-space: pre-line;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  line-height: 1.45;
  font-size: 12px;
  color: var(--el-text-color-regular);
}
.col-picker {
  display: flex;
  flex-direction: column;
  gap: 8px;
  :deep(.el-checkbox) {
    display: flex;
    margin-right: 0;
    width: 100%;
  }
}
.step-row {
  display: grid;
  grid-template-columns: 1fr 1fr auto;
  gap: 8px;
  margin-bottom: 8px;
  width: 100%;
}
.edit-form {
  max-height: 65vh;
  overflow-y: auto;
  padding-right: 8px;
}
.dup-empty { padding: 24px; text-align: center; color: var(--el-text-color-secondary); }
.dup-actions {
  margin-top: 16px;
  padding-bottom: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.dup-collapse {
  :deep(.el-collapse-item__header) {
    height: auto;
    min-height: 56px;
    line-height: 1.4;
    padding: 8px 0;
  }
  :deep(.el-collapse-item__arrow) {
    margin-top: 8px;
  }
}
.dup-group-title {
  flex: 1;
  min-width: 0;
  padding-right: 12px;
  text-align: left;
}
.dup-group-line1 {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 4px;
}
.dup-module {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.dup-group-line2 {
  font-size: 13px;
  color: var(--el-text-color-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  word-break: break-all;
}
</style>
