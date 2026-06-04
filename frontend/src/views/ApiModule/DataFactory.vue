<template>
  <PageCard>
    <template #title>
      <div class="page-title-row">
        <span>数据工厂</span>
      </div>
    </template>
    <template #main>
      <el-alert type="info" :closable="false" show-icon style="margin-bottom: 16px;">
        <template #title>
          配置环境级数据库连接与 SQL 模板，供接口套件造数/清数及数据库断言使用。
        </template>
        <p class="page-tip">断言仅允许 SELECT；造数/清数模板需启用「允许写操作」的数据源。</p>
      </el-alert>

      <el-tabs v-model="activeTab">
        <el-tab-pane label="数据源" name="datasource">
          <div class="search-bar">
            <el-select v-model="dsFilterEnvId" clearable placeholder="筛选环境" style="width: 200px;" @change="loadDatasources">
              <el-option v-for="e in proStore.envList" :key="e.id" :label="e.name" :value="e.id" />
            </el-select>
            <el-button type="primary" icon="Plus" @click="openDsDialog()">新建数据源</el-button>
            <el-button icon="RefreshRight" @click="loadDatasources">刷新</el-button>
          </div>
          <el-table :data="datasourceList" stripe border v-loading="dsLoading">
            <el-table-column prop="name" label="名称" min-width="120" />
            <el-table-column prop="environment_name" label="环境" width="120" />
            <el-table-column label="连接" min-width="200">
              <template #default="{ row }">{{ row.username }}@{{ row.host }}:{{ row.port }}/{{ row.database_name }}</template>
            </el-table-column>
            <el-table-column label="写操作" width="80" align="center">
              <template #default="{ row }">
                <el-tag size="small" :type="row.allow_write ? 'warning' : 'success'">{{ row.allow_write ? '允许' : '只读' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="默认" width="70" align="center">
              <template #default="{ row }">
                <el-tag v-if="row.is_default" size="small" type="primary">默认</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="220" fixed="right">
              <template #default="{ row }">
                <el-button size="small" type="success" link @click="testDs(row)">测试</el-button>
                <el-button size="small" type="primary" link @click="openDsDialog(row)">编辑</el-button>
                <el-button size="small" type="danger" link @click="deleteDs(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="SQL 模板" name="template">
          <div class="search-bar">
            <el-select v-model="tplFilterEnvId" clearable placeholder="筛选环境" style="width: 180px;" @change="loadTemplates">
              <el-option v-for="e in proStore.envList" :key="e.id" :label="e.name" :value="e.id" />
            </el-select>
            <el-select v-model="tplFilterType" clearable placeholder="类型" style="width: 140px;" @change="loadTemplates">
              <el-option label="前置 setup" value="setup" />
              <el-option label="后置 teardown" value="teardown" />
              <el-option label="查询 query" value="query" />
            </el-select>
            <el-button type="primary" icon="Plus" @click="openTplDialog()">新建模板</el-button>
            <el-button icon="RefreshRight" @click="loadTemplates">刷新</el-button>
          </div>
          <el-table :data="templateList" stripe border v-loading="tplLoading">
            <el-table-column prop="name" label="名称" min-width="140" />
            <el-table-column prop="template_type" label="类型" width="100">
              <template #default="{ row }">
                <el-tag size="small">{{ typeLabel(row.template_type) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="datasource_name" label="数据源" width="120" />
            <el-table-column prop="environment_name" label="环境" width="100" />
            <el-table-column prop="description" label="描述" min-width="120" show-overflow-tooltip />
            <el-table-column label="操作" width="200" fixed="right">
              <template #default="{ row }">
                <el-button size="small" type="success" link @click="debugTpl(row)">调试</el-button>
                <el-button size="small" type="primary" link @click="openTplDialog(row)">编辑</el-button>
                <el-button size="small" type="danger" link @click="deleteTpl(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </template>
  </PageCard>

  <!-- 数据源弹窗 -->
  <el-dialog v-model="dsDialogVisible" :title="dsEditingId ? '编辑数据源' : '新建数据源'" width="640px" destroy-on-close>
    <el-form ref="dsFormRef" :model="dsForm" :rules="dsRules" label-width="120px">
      <el-form-item label="名称" prop="name"><el-input v-model="dsForm.name" /></el-form-item>
      <el-form-item label="环境" prop="environment_id">
        <el-select v-model="dsForm.environment_id" style="width: 100%;" :disabled="!!dsEditingId">
          <el-option v-for="e in proStore.envList" :key="e.id" :label="e.name" :value="e.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="主机" prop="host">
        <el-input v-model="dsForm.host" placeholder="Docker 部署填 mysql；本机填 127.0.0.1" />
      </el-form-item>
      <el-form-item label="端口" prop="port">
        <el-input-number
          v-model="dsForm.port"
          :min="1"
          :max="65535"
          controls-position="right"
          class="port-input"
        />
      </el-form-item>
      <el-form-item label="数据库" prop="database_name"><el-input v-model="dsForm.database_name" /></el-form-item>
      <el-form-item label="用户名" prop="username"><el-input v-model="dsForm.username" /></el-form-item>
      <el-form-item label="密码" prop="password">
        <el-input
          v-model="dsForm.password"
          type="password"
          show-password
          :placeholder="dsEditingId ? (dsHasPassword ? '留空则不修改' : '请填写数据库密码') : '请填写数据库密码'"
        />
      </el-form-item>
      <el-form-item label="超时(秒)">
        <el-input-number v-model="dsForm.timeout_seconds" :min="1" :max="120" controls-position="right" class="port-input" />
      </el-form-item>
      <el-form-item label="最大行数">
        <el-input-number v-model="dsForm.max_rows" :min="1" :max="1000" controls-position="right" class="port-input" />
      </el-form-item>
      <el-form-item label="选项">
        <el-checkbox v-model="dsForm.allow_write">允许写操作 (INSERT/UPDATE/DELETE)</el-checkbox>
        <el-checkbox v-model="dsForm.is_default">设为环境默认数据源</el-checkbox>
        <el-checkbox v-model="dsForm.is_enabled">启用</el-checkbox>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dsDialogVisible = false">取消</el-button>
      <el-button type="success" @click="testDsForm" :loading="dsTesting">测试连接</el-button>
      <el-button type="primary" @click="saveDs" :loading="dsSaving">保存</el-button>
    </template>
  </el-dialog>

  <!-- SQL 模板弹窗 -->
  <el-dialog v-model="tplDialogVisible" :title="tplEditingId ? '编辑 SQL 模板' : '新建 SQL 模板'" width="720px" destroy-on-close>
    <el-form ref="tplFormRef" :model="tplForm" :rules="tplRules" label-width="100px">
      <el-form-item label="名称" prop="name"><el-input v-model="tplForm.name" /></el-form-item>
      <el-form-item label="类型" prop="template_type">
        <el-radio-group v-model="tplForm.template_type">
          <el-radio value="setup">前置 setup</el-radio>
          <el-radio value="teardown">后置 teardown</el-radio>
          <el-radio value="query">查询 query</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="数据源" prop="datasource_id">
        <el-select v-model="tplForm.datasource_id" style="width: 100%;" filterable>
          <el-option v-for="ds in datasourceList" :key="ds.id" :label="`${ds.name} (${ds.environment_name})`" :value="ds.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="SQL" prop="sql_text">
        <el-input v-model="tplForm.sql_text" type="textarea" :rows="8" placeholder="支持 ${{变量名}} 替换" style="font-family: monospace;" />
      </el-form-item>
      <el-form-item label="描述"><el-input v-model="tplForm.description" type="textarea" :rows="2" /></el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="tplDialogVisible = false">取消</el-button>
      <el-button type="primary" @click="saveTpl" :loading="tplSaving">保存</el-button>
    </template>
  </el-dialog>

  <!-- 调试结果 -->
  <el-dialog v-model="debugVisible" title="SQL 调试结果" width="700px">
    <pre class="debug-result">{{ debugResultText }}</pre>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { dataFactoryApi } from '@/api/modules/dataFactory'
import PageCard from '@/components/PageCard.vue'

const route = useRoute()
const proStore = ProjectStore()
const projectId = computed(() => Number(route.params.projectId) || proStore.projectInfo.id)

const activeTab = ref('datasource')
const dsLoading = ref(false)
const tplLoading = ref(false)
const datasourceList = ref([])
const templateList = ref([])
const dsFilterEnvId = ref(null)
const tplFilterEnvId = ref(null)
const tplFilterType = ref(null)

const dsDialogVisible = ref(false)
const dsEditingId = ref(null)
const dsHasPassword = ref(false)
const dsSaving = ref(false)
const dsTesting = ref(false)
const dsFormRef = ref()
const dsForm = reactive({
  name: '', environment_id: null, host: 'mysql', port: 3306,
  database_name: '', username: '', password: '', allow_write: false,
  max_rows: 100, timeout_seconds: 10, is_default: false, is_enabled: true,
})
const dsRules = {
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }],
  environment_id: [{ required: true, message: '请选择环境', trigger: 'change' }],
  host: [{ required: true, message: '请输入主机', trigger: 'blur' }],
  port: [{ required: true, message: '请输入端口', trigger: 'change' }],
  database_name: [{ required: true, message: '请输入数据库名', trigger: 'blur' }],
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{
    validator: (_rule, value, callback) => {
      if (dsEditingId.value) {
        callback()
        return
      }
      if (!value?.trim()) {
        callback(new Error('请填写数据库密码'))
        return
      }
      callback()
    },
    trigger: 'blur',
  }],
}

const tplDialogVisible = ref(false)
const tplEditingId = ref(null)
const tplSaving = ref(false)
const tplFormRef = ref()
const tplForm = reactive({
  name: '', template_type: 'setup', datasource_id: null, sql_text: '', description: '',
})
const tplRules = {
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }],
  template_type: [{ required: true, message: '请选择类型', trigger: 'change' }],
  datasource_id: [{ required: true, message: '请选择数据源', trigger: 'change' }],
  sql_text: [{ required: true, message: '请输入 SQL', trigger: 'blur' }],
}

const debugVisible = ref(false)
const debugResultText = ref('')

function typeLabel(t) {
  return { setup: '前置', teardown: '后置', query: '查询' }[t] || t
}

async function loadDatasources() {
  dsLoading.value = true
  try {
    const res = await dataFactoryApi.listDatasources({
      project_id: projectId.value,
      environment_id: dsFilterEnvId.value || undefined,
      size: 100,
    })
    datasourceList.value = res.data?.list || []
  } finally {
    dsLoading.value = false
  }
}

async function loadTemplates() {
  tplLoading.value = true
  try {
    const res = await dataFactoryApi.listSqlTemplates({
      project_id: projectId.value,
      environment_id: tplFilterEnvId.value || undefined,
      template_type: tplFilterType.value || undefined,
      size: 200,
    })
    templateList.value = res.data?.list || []
  } finally {
    tplLoading.value = false
  }
}

function resetDsForm() {
  dsHasPassword.value = false
  Object.assign(dsForm, {
    name: '', environment_id: proStore.envList[0]?.id || null, host: 'mysql', port: 3306,
    database_name: '', username: '', password: '', allow_write: false,
    max_rows: 100, timeout_seconds: 10, is_default: false, is_enabled: true,
  })
}

function buildDsPayload() {
  const payload = { ...dsForm, project_id: projectId.value }
  const pwd = payload.password?.trim()
  if (pwd) {
    payload.password = pwd
  } else {
    delete payload.password
  }
  return payload
}

function openDsDialog(row) {
  dsEditingId.value = row?.id || null
  dsHasPassword.value = !!row?.has_password
  if (row) {
    Object.assign(dsForm, {
      name: row.name, environment_id: row.environment_id, host: row.host, port: row.port,
      database_name: row.database_name, username: row.username, password: '',
      allow_write: row.allow_write, max_rows: row.max_rows, timeout_seconds: row.timeout_seconds,
      is_default: row.is_default, is_enabled: row.is_enabled,
    })
  } else {
    resetDsForm()
  }
  dsDialogVisible.value = true
}

async function saveDs() {
  await dsFormRef.value.validate()
  if (!dsEditingId.value && !dsForm.password?.trim()) {
    ElMessage.warning('请填写数据库密码')
    return
  }
  dsSaving.value = true
  try {
    const payload = buildDsPayload()
    if (dsEditingId.value) {
      await dataFactoryApi.updateDatasource(dsEditingId.value, payload)
    } else {
      if (!payload.password) {
        ElMessage.warning('请填写数据库密码')
        return
      }
      await dataFactoryApi.createDatasource(payload)
    }
    ElMessage.success('保存成功')
    dsDialogVisible.value = false
    await loadDatasources()
  } finally {
    dsSaving.value = false
  }
}

async function testDs(row) {
  const res = await dataFactoryApi.testDatasource(row.id)
  if (res.data?.success) ElMessage.success('连接成功')
  else ElMessage.error(res.data?.error || '连接失败')
}

async function testDsForm() {
  await dsFormRef.value.validate()
  const pwd = dsForm.password?.trim()
  if (!dsEditingId.value && !pwd) {
    ElMessage.warning('请填写数据库密码')
    return
  }
  if (dsEditingId.value && !pwd && !dsHasPassword.value) {
    ElMessage.warning('请填写数据库密码')
    return
  }
  dsTesting.value = true
  try {
    let res
    if (dsEditingId.value) {
      res = await dataFactoryApi.testDatasource(dsEditingId.value, pwd ? { password: pwd } : {})
    } else {
      res = await dataFactoryApi.testConnectionPreview(buildDsPayload())
    }
    if (res.data?.success) ElMessage.success('连接成功')
    else ElMessage.error(res.data?.error || '连接失败')
  } finally {
    dsTesting.value = false
  }
}

async function deleteDs(row) {
  await ElMessageBox.confirm(`确定删除数据源「${row.name}」？`, '提示', { type: 'warning' })
  await dataFactoryApi.deleteDatasource(row.id)
  ElMessage.success('已删除')
  loadDatasources()
}

function openTplDialog(row) {
  tplEditingId.value = row?.id || null
  if (row) {
    Object.assign(tplForm, {
      name: row.name, template_type: row.template_type, datasource_id: row.datasource_id,
      sql_text: row.sql_text, description: row.description || '',
    })
  } else {
    Object.assign(tplForm, { name: '', template_type: 'setup', datasource_id: null, sql_text: '', description: '' })
  }
  tplDialogVisible.value = true
}

async function saveTpl() {
  await tplFormRef.value.validate()
  tplSaving.value = true
  try {
    const payload = { ...tplForm, project_id: projectId.value }
    if (tplEditingId.value) await dataFactoryApi.updateSqlTemplate(tplEditingId.value, payload)
    else await dataFactoryApi.createSqlTemplate(payload)
    ElMessage.success('保存成功')
    tplDialogVisible.value = false
    loadTemplates()
  } finally {
    tplSaving.value = false
  }
}

async function deleteTpl(row) {
  await ElMessageBox.confirm(`确定删除模板「${row.name}」？`, '提示', { type: 'warning' })
  await dataFactoryApi.deleteSqlTemplate(row.id)
  ElMessage.success('已删除')
  loadTemplates()
}

async function debugTpl(row) {
  const envId = row.environment_id || datasourceList.value.find(d => d.id === row.datasource_id)?.environment_id
  const res = await dataFactoryApi.executeTemplate({
    project_id: projectId.value,
    environment_id: envId,
    template_id: row.id,
    variables: {},
  })
  debugResultText.value = JSON.stringify(res.data, null, 2)
  debugVisible.value = true
}

onMounted(async () => {
  if (!proStore.envList?.length) await proStore.getEnvList(projectId.value)
  await loadDatasources()
  await loadTemplates()
})
</script>

<style scoped>
.search-bar {
  display: flex;
  gap: 10px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.page-tip { margin: 4px 0 0; font-size: 13px; color: #606266; }
.port-input {
  width: 200px;
}
.debug-result {
  background: #f5f7fa;
  padding: 12px;
  border-radius: 4px;
  max-height: 400px;
  overflow: auto;
  font-size: 12px;
}
</style>
