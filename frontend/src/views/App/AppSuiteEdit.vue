<template>
  <el-container class="suite-edit-container">
    <KeywordSidebar
      v-model="activeGroups"
      title="前置步骤操作"
      hint="拖到中间步骤区，或双击快速添加"
      :groups="keywordGroups"
      enable-dblclick
      @add="addKeywordToPreActions"
    />

    <div class="suite-workspace">
      <div class="suite-main">
        <el-card class="suite-card">
          <div class="card-header">
            <h2>{{ isEdit ? '编辑 App 套件' : '新建 App 套件' }}</h2>
          </div>

          <el-form :model="suiteInfo" :rules="formRules" ref="formRef" label-width="100px" class="suite-form">
            <el-form-item label="套件名称" prop="name">
              <el-input v-model="suiteInfo.name" placeholder="请输入套件名称" />
            </el-form-item>
            <el-form-item label="套件类型" prop="suite_type">
              <el-select v-model="suiteInfo.suite_type" placeholder="请选择套件类型" style="width: 100%">
                <el-option label="功能测试" value="1" />
                <el-option label="场景测试" value="2" />
              </el-select>
            </el-form-item>
            <el-form-item label="执行策略">
              <div class="suite-strategy-box">
                <el-checkbox v-model="suiteInfo.propagate_variables">
                  链路变量传递（前序用例变量可供后续用例使用）
                </el-checkbox>
                <el-checkbox v-model="suiteInfo.stop_on_failure">
                  失败即停（某用例失败后跳过后续用例）
                </el-checkbox>
              </div>
            </el-form-item>
            <el-form-item label="所属目录" prop="catalog_id">
              <CatalogTreeSelect
                v-model="suiteInfo.catalog_id"
                :project-id="proStore.projectInfo.id"
                placeholder="请选择所属目录"
              />
            </el-form-item>
            <el-form-item label="创建人">
              <el-input v-model="suiteInfo.username" disabled />
            </el-form-item>
          </el-form>

          <div class="setup-steps-section">
            <div class="section-title">
              <span>公共前置步骤</span>
              <el-button size="small" plain type="primary" @click="fragmentPickerVisible = true">插入片段</el-button>
              <el-text type="info" size="small">拖拽左侧操作到此处</el-text>
            </div>
            <StepEditor
              v-model:steps="suiteInfo.pre_actions"
              module="app"
              :debug-selected-index="selectedStepIndex"
              @debug-select-step="selectedStepIndex = $event"
            />
          </div>

          <FragmentPickerDialog
            v-model="fragmentPickerVisible"
            domain="app"
            :selected-step-index="selectedStepIndex"
            :steps-count="suiteInfo.pre_actions?.length || 0"
            @insert="onFragmentInsert"
          />

          <el-collapse class="suite-hooks-collapse">
            <el-collapse-item title="数据工厂（前置/后置 SQL）" name="sql">
              <el-alert type="info" :closable="false" show-icon style="margin-bottom: 12px;">
                可在
                <el-link type="primary" @click="router.push('/data-factory')">数据工厂</el-link>
                维护 SQL 模板；步骤中亦可用 <code v-pre>${{dt:模板名}}</code> 引用数据工具。
              </el-alert>
              <el-form-item label="前置 SQL">
                <el-select v-model="suiteInfo.setup_sql_ids" multiple filterable placeholder="选择 setup 模板" style="width: 100%">
                  <el-option v-for="t in setupTemplates" :key="t.id" :label="t.name" :value="t.id" />
                </el-select>
              </el-form-item>
              <el-form-item label="后置 SQL">
                <el-select v-model="suiteInfo.teardown_sql_ids" multiple filterable placeholder="选择 teardown 模板" style="width: 100%">
                  <el-option v-for="t in teardownTemplates" :key="t.id" :label="t.name" :value="t.id" />
                </el-select>
              </el-form-item>
            </el-collapse-item>
            <el-collapse-item title="套件级数据库断言" name="db">
              <DbAssertionsEditor v-model="suiteInfo.db_assertions" :datasources="datasources" />
            </el-collapse-item>
          </el-collapse>

          <div class="action-bar">
            <el-button type="primary" :loading="saving" @click="saveSuite">
              <el-icon><Check /></el-icon>
              保存
            </el-button>
            <el-button @click="goBack">
              <el-icon><Close /></el-icon>
              取消
            </el-button>
          </div>
        </el-card>
      </div>

      <div
        class="panel-resizer"
        :class="{ 'is-active': isResizing }"
        title="拖拽调整宽度"
        @mousedown="onResizeStart"
      />

      <aside class="case-sidebar" :style="{ width: `${rightWidth}px` }">
        <div class="case-section">
          <h3 class="sidebar-title">套件用例</h3>
          <AppSuiteCaseList
            ref="suiteCaseListRef"
            :suite-id="suiteId || null"
            @cases-change="onSuiteCasesChange"
          />
        </div>
        <div class="case-section">
          <h3 class="sidebar-title">App 用例集</h3>
          <AppCaseSet :suite-id="suiteId || null" />
        </div>
      </aside>
    </div>
  </el-container>
</template>

<script setup>
import { computed, onMounted, provide, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElNotification } from 'element-plus'
import { StepEditor, KeywordSidebar } from '@/components/StepEditor'
import CatalogTreeSelect from '@/components/CatalogTreeSelect.vue'
import FragmentPickerDialog from '@/components/StepEditor/FragmentPickerDialog.vue'
import DbAssertionsEditor from '@/views/ApiModule/components/DbAssertionsEditor.vue'
import AppSuiteCaseList from '@/views/App/components/AppSuiteCaseList.vue'
import AppCaseSet from '@/views/App/components/AppCaseSet.vue'
import appActionGroup from '@/datas/AppActionGroup.js'
import { appSuiteApi } from '@/api'
import { dataFactoryApi } from '@/api/modules/dataFactory'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { UserStore } from '@/stores/module/UserStore'
import {
  buildStepFromKeyword,
  ensureStepsHaveIds,
  serializeKeywordForDrag,
  insertStepIntoList,
  resolveInsertAfterIndex,
} from '@/utils/stepHelper'
import { useSplitPanelResize } from '@/composables/useSplitPanelResize'
import {
  Check, Close, Document, Edit, Mouse, Clock, Search, MessageBox, MoreFilled, Share,
} from '@element-plus/icons-vue'

const { rightWidth, isResizing, onResizeStart } = useSplitPanelResize({
  storageKey: 'app-suite-edit-right-panel-width',
  defaultWidth: 560,
})

const route = useRoute()
const router = useRouter()
const proStore = ProjectStore()
const userStore = UserStore()
const suiteId = route.params.id
const isEdit = computed(() => !!suiteId)

const formRef = ref()
const suiteCaseListRef = ref()
const saving = ref(false)
const fragmentPickerVisible = ref(false)
const selectedStepIndex = ref(-1)
const suiteAddedCaseIds = ref(new Set())
const varInsertEnvId = ref(proStore.envList[0]?.id || null)

provide('suiteAddedCaseIds', suiteAddedCaseIds)
provide('varInsertEnvId', varInsertEnvId)

const activeGroups = ref(['1', '2', '3', '4', '5', '6', '6b', '7', '8'])
const iconMap = { Document, Edit, Mouse, Clock, Search, MessageBox, MoreFilled, Share }

const suiteInfo = reactive({
  name: '',
  suite_type: '1',
  catalog_id: null,
  username: userStore.userInfo?.username || '',
  pre_actions: [],
  setup_sql_ids: [],
  teardown_sql_ids: [],
  db_assertions: [],
  stop_on_failure: false,
  propagate_variables: false,
})

const datasources = ref([])
const sqlTemplates = ref([])
const setupTemplates = computed(() => sqlTemplates.value.filter((t) => t.phase === 'setup'))
const teardownTemplates = computed(() => sqlTemplates.value.filter((t) => t.phase === 'teardown'))

const formRules = {
  name: [{ required: true, message: '请输入套件名称', trigger: 'blur' }],
  suite_type: [{ required: true, message: '请选择套件类型', trigger: 'change' }],
}

const keywordGroups = computed(() =>
  appActionGroup.map((group) => ({
    ...group,
    icon: iconMap[group.groupIcon] || Document,
    items: group.items.map((item) => ({
      name: item.keyword,
      keyword: item.keyword,
      method: item.method,
      icon: iconMap[group.groupIcon] || Document,
      params: { ...item.params },
      is_container: item.is_container,
      branches: item.branches,
    })),
  }))
)

function addKeywordToPreActions(item) {
  const raw = JSON.parse(serializeKeywordForDrag(item))
  suiteInfo.pre_actions = [...(suiteInfo.pre_actions || []), buildStepFromKeyword(raw)]
}

function onSuiteCasesChange(caseIds) {
  suiteAddedCaseIds.value = new Set(caseIds)
}

function onFragmentInsert(payload) {
  const refStep = payload?.step || payload
  if (!refStep) return
  const insertAt = payload?.insertAt ?? resolveInsertAfterIndex(suiteInfo.pre_actions?.length || 0, selectedStepIndex.value)
  const { steps, insertAt: at } = insertStepIntoList(suiteInfo.pre_actions, refStep, insertAt)
  suiteInfo.pre_actions = steps
  selectedStepIndex.value = at
  ElMessage.success(`已在第 ${at + 1} 步插入片段「${refStep.params?.fragment_name || refStep.desc}」`)
}

async function loadFactoryMeta() {
  if (!proStore.projectInfo?.id) return
  try {
    const [dsRes, tplRes] = await Promise.all([
      dataFactoryApi.listDatasources({ project_id: proStore.projectInfo.id, size: 100 }),
      dataFactoryApi.listSqlTemplates({ project_id: proStore.projectInfo.id, size: 200 }),
    ])
    datasources.value = dsRes.data?.list || []
    sqlTemplates.value = tplRes.data?.list || []
  } catch {
    datasources.value = []
    sqlTemplates.value = []
  }
}

async function loadDetail() {
  if (!suiteId) return
  const res = await appSuiteApi.detail(suiteId)
  const data = res.data || {}
  suiteInfo.name = data.name || ''
  suiteInfo.suite_type = data.suite_type || '1'
  suiteInfo.catalog_id = data.catalog_id ?? null
  suiteInfo.username = data.username || userStore.userInfo?.username || ''
  suiteInfo.pre_actions = ensureStepsHaveIds(Array.isArray(data.pre_actions) ? data.pre_actions : [])
  suiteInfo.setup_sql_ids = data.setup_sql_ids || []
  suiteInfo.teardown_sql_ids = data.teardown_sql_ids || []
  suiteInfo.db_assertions = Array.isArray(data.db_assertions) ? data.db_assertions.map((a) => ({ ...a })) : []
  suiteInfo.stop_on_failure = !!data.stop_on_failure
  suiteInfo.propagate_variables = !!data.propagate_variables
}

async function saveSuite() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  saving.value = true
  try {
    const payload = {
      ...suiteInfo,
      project_id: proStore.projectInfo.id,
      username: userStore.userInfo?.username,
    }
    let id = suiteId
    if (isEdit.value) {
      await appSuiteApi.update(suiteId, payload)
    } else {
      const res = await appSuiteApi.create(payload)
      id = res.data?.id
    }

    if (suiteCaseListRef.value && id) {
      const ok = await suiteCaseListRef.value.saveSuiteCases(id)
      if (!ok) return
    }

    ElNotification.success('套件保存成功')
    goBack()
  } catch (error) {
    ElNotification.error(error?.response?.data?.detail || '保存套件失败')
  } finally {
    saving.value = false
  }
}

function goBack() {
  router.back()
  userStore.deleteTabs(route.path)
}

onMounted(async () => {
  if (!varInsertEnvId.value && proStore.envList.length) {
    varInsertEnvId.value = proStore.envList[0].id
  }
  await loadFactoryMeta()
  await loadDetail()
})
</script>

<style scoped lang="scss">
@use '@/styles/suite-edit-layout.scss';
@use '@/styles/case-step-editor-layout.scss';

.sidebar-hint {
  margin: 6px 0 0;
  font-size: 12px;
  font-weight: normal;
  color: var(--el-text-color-secondary);
}

.suite-strategy-box {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}

.suite-hooks-collapse {
  margin-top: 16px;
}

.setup-steps-section .section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
</style>
