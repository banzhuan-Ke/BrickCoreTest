<template>
  <PageCard>
    <template #title>
      <div class="page-title-row">
        <span>Token 授权管理</span>
        <el-button type="primary" size="small" icon="Plus" @click="openDialog()">新建授权</el-button>
      </div>
    </template>
    <template #main>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        style="margin-bottom: 16px;"
      >
        <template #title>
          配置登录 Token 后，用例执行前自动注入 <code v-pre>${{token}}</code> 等变量；过期时自动刷新。
        </template>
        <p class="page-tip">一般请用<strong>接口登录</strong>；Token 已在环境 global_vars 时，可直接在用例里写 <code v-pre>${{变量名}}</code>，不必建授权。</p>
      </el-alert>

      <el-alert
        type="warning"
        :closable="false"
        show-icon
        style="margin-bottom: 16px;"
      >
        <template #title>变量优先级（同名变量）</template>
        <p class="page-tip priority-tip">
          合并顺序（低→高）：项目全局变量 → 环境变量 → 套件前序用例提取 →
          <strong>Token 授权</strong> → 前置脚本。
          启用本页授权后，<strong>授权变量会覆盖</strong>环境与套件传递的同名 token。
          请勿与「套件第一条登录用例 extract token」同时使用同名变量，请<strong>二选一</strong>。
          多角色请用不同变量名（如 <code v-pre>admin_token</code> / <code v-pre>user_token</code>）。
        </p>
      </el-alert>

      <div class="search-bar">
        <el-select
          v-model="filterEnvId"
          clearable
          placeholder="筛选环境"
          style="width: 200px;"
          @change="loadList"
        >
          <el-option v-for="e in proStore.envList" :key="e.id" :label="e.name" :value="e.id" />
        </el-select>
        <el-input v-model="keyword" placeholder="搜索名称" clearable style="width: 200px;" @keyup.enter="loadList" />
        <el-button type="primary" icon="Search" @click="loadList">搜索</el-button>
        <el-button icon="RefreshRight" @click="resetSearch">重置</el-button>
      </div>

      <el-table :data="authList" stripe v-loading="loading" border>
        <el-table-column prop="name" label="授权名称" min-width="140" show-overflow-tooltip />
        <el-table-column prop="environment_name" label="环境" width="120" />
        <el-table-column label="方式" width="110">
          <template #default="{ row }">
            <el-tag size="small" :type="row.auth_type === 'api_login' ? 'primary' : 'warning'">
              {{ row.auth_type === 'api_login' ? '接口登录' : '自定义代码' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="login_api_name" label="登录接口" min-width="140" show-overflow-tooltip>
          <template #default="{ row }">{{ row.login_api_name || '—' }}</template>
        </el-table-column>
        <el-table-column label="缓存剩余" width="100" align="center">
          <template #default="{ row }">
            <span v-if="row.cache_remaining_minutes != null">{{ row.cache_remaining_minutes }} 分</span>
            <span v-else class="muted">未刷新</span>
          </template>
        </el-table-column>
        <el-table-column label="启用" width="80" align="center">
          <template #default="{ row }">
            <el-switch :model-value="row.is_enabled" @change="v => toggleEnabled(row, v)" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="280" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" link @click="openDialog(row)">编辑</el-button>
            <el-button size="small" type="success" link :loading="row._refreshing" @click="handleRefresh(row)">刷新</el-button>
            <el-button size="small" type="info" link @click="showCache(row)">缓存</el-button>
            <el-button size="small" type="warning" link @click="handleClearCache(row)">清空</el-button>
            <el-button size="small" type="danger" link @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-model:current-page="pagination.page"
        v-model:page-size="pagination.size"
        :total="pagination.total"
        :page-sizes="[10, 20, 50]"
        layout="total, sizes, prev, pager, next"
        class="pagination"
        @size-change="loadList"
        @current-change="loadList"
      />
    </template>
  </PageCard>

  <el-dialog v-model="dialogVisible" :title="dialogTitle" width="720px" destroy-on-close @closed="resetForm">
    <el-form ref="formRef" :model="form" :rules="rules" label-width="120px">
      <el-form-item label="授权名称" prop="name">
        <el-input v-model="form.name" placeholder="如：测试环境登录 Token" />
      </el-form-item>
      <el-form-item label="环境" prop="environment_id">
        <el-select v-model="form.environment_id" placeholder="选择环境" style="width: 100%;" :disabled="!!editingId">
          <el-option v-for="e in proStore.envList" :key="e.id" :label="e.name" :value="e.id" />
        </el-select>
      </el-form-item>

      <template v-if="form.auth_type === 'api_login'">
        <el-form-item label="登录接口" prop="login_api_id">
          <el-select
            v-model="form.login_api_id"
            filterable
            placeholder="选择接口定义"
            style="width: 100%;"
            :loading="apiLoading"
          >
            <el-option v-for="a in apiList" :key="a.id" :label="`${a.method} ${a.name}`" :value="a.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="变量提取">
          <div class="extractor-list">
            <div v-for="(ex, idx) in form.extractors" :key="idx" class="extractor-row">
              <el-input v-model="ex.name" placeholder="变量名 token" style="width: 120px;" />
              <el-select v-model="ex.source" style="width: 100px;">
                <el-option label="JSON" value="json" />
                <el-option label="Header" value="header" />
                <el-option label="正则" value="regex" />
              </el-select>
              <el-input v-model="ex.path" placeholder="$.data.token 或 Header 名" style="flex: 1;" />
              <el-button icon="Delete" type="danger" link @click="form.extractors.splice(idx, 1)" />
            </div>
            <el-button size="small" @click="addExtractor">+ 添加提取规则</el-button>
          </div>
        </el-form-item>
      </template>

      <template v-else>
        <el-alert type="warning" :closable="false" show-icon class="custom-code-tip">
          <template #title>自定义代码（高级）</template>
          <p>仅适合从环境 global_vars 拼变量或固定 Token，<strong>不能发 HTTP</strong>。需要调登录接口请改回「接口登录」。</p>
        </el-alert>
        <el-form-item label="授权代码">
          <el-input v-model="form.custom_code" type="textarea" :rows="12" class="code-area" />
        </el-form-item>
      </template>

      <el-collapse v-model="advancedOpen" class="advanced-collapse">
        <el-collapse-item name="advanced" title="高级选项">
          <p class="advanced-hint">一般请用<strong>接口登录</strong>或<strong>环境变量</strong>；下列自定义代码仅供特殊场景。</p>
          <el-form-item label="授权方式" label-width="120px">
            <el-radio-group v-model="form.auth_type">
              <el-radio value="api_login">接口登录（推荐）</el-radio>
              <el-radio value="custom_code">自定义代码</el-radio>
            </el-radio-group>
          </el-form-item>
        </el-collapse-item>
      </el-collapse>

      <el-form-item label="有效期(分钟)">
        <el-input-number v-model="form.ttl_minutes" :min="1" :max="10080" />
      </el-form-item>
      <el-form-item label="提前刷新(分钟)">
        <el-input-number v-model="form.refresh_before_minutes" :min="0" :max="120" />
      </el-form-item>
      <el-form-item label="启用">
        <el-switch v-model="form.is_enabled" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="warning" :loading="testing" @click="handleTestPreview">调试授权</el-button>
      <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="testResultVisible" title="授权调试结果" width="560px" append-to-body>
    <el-alert v-if="testResult.error" type="error" :title="testResult.error" show-icon :closable="false" />
    <template v-else>
      <p class="test-hint">{{ testResult.hint }}</p>
      <pre class="cache-json">{{ JSON.stringify(testResult.variables || {}, null, 2) }}</pre>
    </template>
    <template #footer>
      <el-button type="primary" @click="testResultVisible = false">关闭</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="cacheVisible" title="授权缓存" width="560px">
    <el-descriptions :column="1" border size="small" v-if="cacheRow">
      <el-descriptions-item label="授权名称">{{ cacheRow.name }}</el-descriptions-item>
      <el-descriptions-item label="过期时间">{{ cacheRow.cache_expires_at || '—' }}</el-descriptions-item>
      <el-descriptions-item label="剩余分钟">{{ cacheRow.cache_remaining_minutes ?? '—' }}</el-descriptions-item>
      <el-descriptions-item label="最近刷新">{{ cacheRow.last_refresh_time || '—' }}</el-descriptions-item>
      <el-descriptions-item label="最近错误">
        <span :class="{ 'text-danger': cacheRow.last_refresh_error }">{{ cacheRow.last_refresh_error || '—' }}</span>
      </el-descriptions-item>
    </el-descriptions>
    <pre class="cache-json">{{ JSON.stringify(cacheRow?.cache_data || {}, null, 2) }}</pre>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import PageCard from '@/components/PageCard.vue'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { httpAuthConfigApi } from '@/api/modules/httpAuth'
import { httpApi } from '@/api/modules/http'

const proStore = ProjectStore()

const loading = ref(false)
const saving = ref(false)
const testing = ref(false)
const apiLoading = ref(false)
const authList = ref([])
const apiList = ref([])
const keyword = ref('')
const filterEnvId = ref(null)
const pagination = reactive({ page: 1, size: 20, total: 0 })

const dialogVisible = ref(false)
const editingId = ref(null)
const formRef = ref(null)
const advancedOpen = ref([])
const cacheVisible = ref(false)
const cacheRow = ref(null)
const testResultVisible = ref(false)
const testResult = reactive({ variables: null, hint: '', error: '' })

const defaultForm = () => ({
  name: '',
  environment_id: null,
  auth_type: 'api_login',
  login_api_id: null,
  extractors: [{ name: 'token', source: 'json', path: '$.data.token' }],
  custom_code: '',
  ttl_minutes: 1440,
  refresh_before_minutes: 5,
  is_enabled: true
})

function normalizeAuthExtractor(raw) {
  if (!raw || typeof raw !== 'object') return { name: '', source: 'json', path: '' }
  let source = raw.source || raw.type || 'json'
  if (source === 'jsonpath') source = 'json'
  const path = raw.path || raw.expression || raw.property || ''
  return {
    name: raw.name || '',
    source,
    path,
    description: raw.description || '',
  }
}
const form = reactive(defaultForm())

const rules = {
  name: [{ required: true, message: '请输入授权名称', trigger: 'blur' }],
  environment_id: [{ required: true, message: '请选择环境', trigger: 'change' }],
  login_api_id: [{
    validator: (_r, v, cb) => {
      if (form.auth_type === 'api_login' && !v) cb(new Error('请选择登录接口'))
      else cb()
    },
    trigger: 'change'
  }]
}

const dialogTitle = computed(() => (editingId.value ? '编辑授权配置' : '新建授权配置'))
const projectId = computed(() => proStore.projectInfo?.id)

const loadEnvs = async () => {
  if (!projectId.value) return
  await proStore.getEnvironmentList()
}

const loadApis = async () => {
  if (!projectId.value) return
  apiLoading.value = true
  try {
    const res = await httpApi.getList({ project_id: projectId.value, page: 1, size: 500 })
    apiList.value = res.data?.data?.list || res.data?.data || []
  } finally {
    apiLoading.value = false
  }
}

const loadList = async () => {
  if (!projectId.value) {
    ElMessage.warning('请先选择项目')
    return
  }
  loading.value = true
  try {
    const params = { project_id: projectId.value, page: pagination.page, size: pagination.size }
    if (filterEnvId.value) params.environment_id = filterEnvId.value
    if (keyword.value) params.keyword = keyword.value
    const res = await httpAuthConfigApi.getList(params)
    if (res.data?.code === 200) {
      authList.value = (res.data.data?.list || []).map(r => ({ ...r, _refreshing: false }))
      pagination.total = res.data.data?.total || 0
    }
  } catch {
    ElMessage.error('加载授权配置失败')
  } finally {
    loading.value = false
  }
}

const resetSearch = () => {
  keyword.value = ''
  filterEnvId.value = null
  pagination.page = 1
  loadList()
}

const addExtractor = () => {
  form.extractors.push({ name: '', source: 'json', path: '' })
}

const openDialog = async (row = null) => {
  if (!projectId.value) {
    ElMessage.warning('请先选择项目')
    return
  }
  await Promise.all([loadEnvs(), loadApis()])
  if (row) {
    editingId.value = row.id
    advancedOpen.value = row.auth_type === 'custom_code' ? ['advanced'] : []
    Object.assign(form, {
      name: row.name,
      environment_id: row.environment_id,
      auth_type: row.auth_type,
      login_api_id: row.login_api_id,
      extractors: JSON.parse(JSON.stringify(
        (row.extractors?.length ? row.extractors : [{ name: 'token', source: 'json', path: '$.data.token' }])
          .map(normalizeAuthExtractor)
      )),
      custom_code: row.custom_code || '',
      ttl_minutes: row.ttl_minutes,
      refresh_before_minutes: row.refresh_before_minutes,
      is_enabled: row.is_enabled
    })
  } else {
    editingId.value = null
    advancedOpen.value = []
    Object.assign(form, defaultForm())
    try {
      const res = await httpAuthConfigApi.getCustomCodeTemplate()
      if (res.data?.code === 200) form.custom_code = res.data.data?.code || ''
    } catch { /* ignore */ }
  }
  dialogVisible.value = true
}

const resetForm = () => {
  editingId.value = null
  advancedOpen.value = []
  Object.assign(form, defaultForm())
}

const handleTestPreview = async () => {
  if (!projectId.value) {
    ElMessage.warning('请先选择项目')
    return
  }
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  testing.value = true
  testResult.error = ''
  testResult.variables = null
  testResult.hint = ''
  try {
    const res = await httpAuthConfigApi.testPreview({
      project_id: projectId.value,
      environment_id: form.environment_id,
      auth_type: form.auth_type,
      login_api_id: form.auth_type === 'api_login' ? form.login_api_id : null,
      extractors: form.auth_type === 'api_login' ? form.extractors.filter(e => e.name) : [],
      custom_code: form.auth_type === 'custom_code' ? form.custom_code : null
    })
    if (res.data?.code === 200) {
      testResult.variables = res.data.data?.variables || {}
      testResult.hint = res.data.data?.usage_hint || ''
      testResultVisible.value = true
      ElMessage.success('调试成功，请核对下方变量')
    } else {
      ElMessage.error(res.data?.message || '调试失败')
    }
  } catch (e) {
    testResult.error = e.response?.data?.detail || e.response?.data?.message || e.message || '调试失败'
    testResultVisible.value = true
  } finally {
    testing.value = false
  }
}

const handleSave = async () => {
  await formRef.value?.validate()
  saving.value = true
  try {
    const payload = {
      project_id: projectId.value,
      environment_id: form.environment_id,
      name: form.name,
      auth_type: form.auth_type,
      login_api_id: form.auth_type === 'api_login' ? form.login_api_id : null,
      extractors: form.auth_type === 'api_login' ? form.extractors.filter(e => e.name) : [],
      custom_code: form.auth_type === 'custom_code' ? form.custom_code : null,
      ttl_minutes: form.ttl_minutes,
      refresh_before_minutes: form.refresh_before_minutes,
      is_enabled: form.is_enabled
    }
    if (editingId.value) {
      const { project_id, environment_id, ...updateBody } = payload
      await httpAuthConfigApi.update(editingId.value, updateBody, projectId.value)
    } else {
      await httpAuthConfigApi.create(payload)
    }
    ElMessage.success('保存成功')
    dialogVisible.value = false
    loadList()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || e.response?.data?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

const handleRefresh = async (row) => {
  row._refreshing = true
  try {
    const res = await httpAuthConfigApi.refresh(row.id, projectId.value)
    if (res.data?.code === 200) {
      ElMessage.success('刷新成功')
      loadList()
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '刷新失败')
  } finally {
    row._refreshing = false
  }
}

const showCache = (row) => {
  cacheRow.value = row
  cacheVisible.value = true
}

const handleClearCache = async (row) => {
  await ElMessageBox.confirm('清空后下次执行将重新刷新授权', '确认清空缓存', { type: 'warning' })
  await httpAuthConfigApi.clearCache(row.id, projectId.value)
  ElMessage.success('已清空')
  loadList()
}

const toggleEnabled = async (row, val) => {
  try {
    await httpAuthConfigApi.update(row.id, { is_enabled: val }, projectId.value)
    row.is_enabled = val
  } catch {
    ElMessage.error('更新失败')
    loadList()
  }
}

const handleDelete = async (row) => {
  await ElMessageBox.confirm(`确定删除授权「${row.name}」？`, '删除确认', { type: 'warning' })
  await httpAuthConfigApi.delete(row.id, projectId.value)
  ElMessage.success('已删除')
  loadList()
}

watch(() => projectId.value, () => {
  loadEnvs()
  loadList()
})

onMounted(() => {
  loadEnvs()
  loadList()
})
</script>

<style scoped>
.page-title-row { display: flex; align-items: center; justify-content: space-between; width: 100%; }
.search-bar { display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }
.pagination { margin-top: 16px; justify-content: flex-end; }
.extractor-list { width: 100%; }
.extractor-row { display: flex; gap: 8px; margin-bottom: 8px; align-items: center; }
.code-area :deep(textarea) { font-family: Consolas, monospace; font-size: 13px; }
.page-tip { margin: 6px 0 0; font-size: 13px; line-height: 1.5; }
.priority-tip { margin: 4px 0 0; }
.priority-tip code { font-size: 12px; }
.advanced-collapse { margin-bottom: 8px; border: none; }
.advanced-collapse :deep(.el-collapse-item__header) {
  height: 40px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
  border-bottom: none;
}
.advanced-collapse :deep(.el-collapse-item__wrap) { border-bottom: none; }
.advanced-hint { margin: 0 0 12px; font-size: 13px; color: var(--el-text-color-secondary); line-height: 1.5; }
.custom-code-tip { margin-bottom: 12px; font-size: 13px; }
.custom-code-tip p { margin: 4px 0; line-height: 1.5; }
.test-hint { font-size: 13px; color: var(--el-text-color-secondary); margin-bottom: 8px; }
.cache-json { margin-top: 12px; background: #f5f7fa; padding: 12px; border-radius: 4px; font-size: 12px; max-height: 240px; overflow: auto; }
.muted { color: #909399; }
.text-danger { color: #f56c6c; }
</style>
