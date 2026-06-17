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
          配置环境级数据库连接、SQL 模板与通用数据工具；保存标签后可在接口/Web/性能场景用例中引用（见通用工具 Tab）。
        </template>
        <p class="page-tip">SQL 工厂：断言仅允许 SELECT；造数/清数需启用「允许写操作」数据源。通用工具可「保存为标签」<code v-pre>${{df:标签名}}</code>，或在接口/Web/压测编辑页用 **「插入工具」** 直接写 <code v-pre>${{dt:...}}</code>（无需保存）。</p>
      </el-alert>

      <el-tabs v-model="activeTab">
        <el-tab-pane label="通用工具" name="toolbox">
          <DataToolBoxPanel :project-id="projectId" @saved="loadToolRecords" />
        </el-tab-pane>

        <el-tab-pane label="使用记录" name="records">
          <div v-if="favoriteTagList.length" class="favorites-bar">
            <span class="favorites-label">常用标签</span>
            <el-tag
              v-for="tag in favoriteTagList"
              :key="tag"
              class="fav-tag"
              effect="plain"
              type="warning"
              @click="filterByFavoriteTag(tag)"
            >{{ tag }}</el-tag>
          </div>
          <div class="search-bar">
            <DfEnvScopeSelect
              v-model="recordFilterEnvId"
              placeholder="筛选范围"
              :style="{ width: '220px' }"
              project-common-label="全部（含项目通用）"
              @update:model-value="loadToolRecords"
            />
            <el-input v-model="recordKeyword" placeholder="标签/工具名" clearable style="width: 180px;" @keyup.enter="loadToolRecords" />
            <el-button type="primary" icon="Search" @click="loadToolRecords">查询</el-button>
            <el-button icon="RefreshRight" @click="loadToolRecords">刷新</el-button>
          </div>
          <el-table :data="toolRecordList" stripe border v-loading="recordLoading">
            <el-table-column label="收藏" width="56" align="center">
              <template #default="{ row }">
                <el-button
                  link
                  :type="isTagFavorited(row.tag) ? 'warning' : 'info'"
                  :icon="isTagFavorited(row.tag) ? 'StarFilled' : 'Star'"
                  @click="toggleTagFavorite(row.tag)"
                />
              </template>
            </el-table-column>
            <el-table-column prop="tag" label="标签" width="140">
              <template #default="{ row }">
                <code>{{ dfRef(row.tag) }}</code>
              </template>
            </el-table-column>
            <el-table-column prop="tool_name" label="工具" width="110" />
            <el-table-column prop="environment_name" label="环境" width="100" />
            <el-table-column prop="output_text" label="输出预览" min-width="160" show-overflow-tooltip />
            <el-table-column label="引用" width="100" align="center">
              <template #default="{ row }">
                <el-popover v-if="row.usage_count" placement="left" width="320" trigger="hover">
                  <template #reference>
                    <el-tag size="small" type="warning">{{ row.usage_count }} 处</el-tag>
                  </template>
                  <div class="usage-popover">
                    <p v-for="(u, i) in row.usages" :key="i" class="usage-line">
                      {{ u.resource_type_label }}：{{ u.resource_name }}
                      <span class="usage-loc">（{{ u.location }}）</span>
                    </p>
                  </div>
                </el-popover>
                <el-text v-else type="info" size="small">未引用</el-text>
              </template>
            </el-table-column>
            <el-table-column prop="remark" label="备注" width="100" show-overflow-tooltip />
            <el-table-column prop="update_time" label="更新时间" width="160" />
            <el-table-column label="操作" width="200" fixed="right">
              <template #default="{ row }">
                <el-button size="small" link type="primary" @click="openRecordEdit(row)">编辑</el-button>
                <el-button size="small" link type="primary" @click="copyTagRef(row.tag)">复制</el-button>
                <el-button
                  size="small"
                  link
                  type="danger"
                  :disabled="row.usage_count > 0"
                  @click="deleteRecord(row)"
                >删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

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
            <el-table-column label="类型" width="100">
              <template #default="{ row }">
                <el-tag size="small">{{ dbTypeLabel(row.db_type) }}</el-tag>
              </template>
            </el-table-column>
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
      <el-form-item label="类型" prop="db_type">
        <el-select v-model="dsForm.db_type" style="width: 100%;" @change="onDbTypeChange">
          <el-option label="MySQL" value="mysql" />
          <el-option label="PostgreSQL" value="postgresql" />
          <el-option label="Redis" value="redis" />
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
      <el-form-item :label="dsDbLabel" prop="database_name">
        <el-input v-model="dsForm.database_name" :placeholder="dsDbPlaceholder" />
      </el-form-item>
      <el-form-item v-if="dsForm.db_type !== 'redis'" label="用户名" prop="username">
        <el-input v-model="dsForm.username" />
      </el-form-item>
      <el-form-item :label="dsForm.db_type === 'redis' ? '密码(可选)' : '密码'" prop="password">
        <el-input
          v-model="dsForm.password"
          type="password"
          show-password
          :placeholder="dsPasswordPlaceholder"
        />
      </el-form-item>
      <el-form-item label="超时(秒)">
        <el-input-number v-model="dsForm.timeout_seconds" :min="1" :max="120" controls-position="right" class="port-input" />
      </el-form-item>
      <el-form-item label="最大行数">
        <el-input-number v-model="dsForm.max_rows" :min="1" :max="1000" controls-position="right" class="port-input" />
      </el-form-item>
      <el-form-item label="选项">
        <el-checkbox v-model="dsForm.allow_write">{{ dsWriteHint }}</el-checkbox>
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
        <MonacoEditor v-if="tplDialogVisible" v-model="tplForm.sql_text" language="sql" height="220px" />
        <p class="field-hint">支持 <code v-pre>${{变量名}}</code> 替换；Redis 数据源请写命令如 SET key value</p>
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

  <!-- 使用记录编辑 -->
  <el-dialog v-model="recordEditVisible" title="编辑使用记录" width="520px" destroy-on-close>
    <el-form label-width="88px">
      <el-form-item label="标签">
        <code>{{ recordEditForm.tagRef }}</code>
      </el-form-item>
      <el-form-item label="工具">
        <span>{{ recordEditForm.tool_name }}</span>
      </el-form-item>
      <el-form-item label="输出预览">
        <el-input :model-value="recordEditForm.output_text" type="textarea" :rows="2" readonly />
      </el-form-item>
      <el-form-item label="环境">
        <DfEnvScopeSelect v-model="recordEditForm.environment_id" style="width: 100%;" />
        <div class="field-hint">可改为项目通用或指定环境；标签名与输出内容不可修改。</div>
      </el-form-item>
      <el-form-item label="备注">
        <el-input v-model="recordEditForm.remark" type="textarea" :rows="2" maxlength="255" show-word-limit placeholder="描述用途，便于团队识别" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="recordEditVisible = false">取消</el-button>
      <el-button type="primary" :loading="recordEditSaving" @click="saveRecordEdit">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import MonacoEditor from '@/components/MonacoEditor'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { dataFactoryApi } from '@/api/modules/dataFactory'
import PageCard from '@/components/PageCard.vue'
import DataToolBoxPanel from './components/DataToolBoxPanel.vue'
import DfEnvScopeSelect from '@/components/DfEnvScopeSelect.vue'

const route = useRoute()
const proStore = ProjectStore()
const projectId = computed(() => Number(route.params.projectId) || proStore.projectInfo.id)

const activeTab = ref('toolbox')
const recordLoading = ref(false)
const toolRecordList = ref([])
const recordFilterEnvId = ref(null)
const recordKeyword = ref('')
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
const favoriteTags = ref(new Set())
const favoriteTagList = computed(() => Array.from(favoriteTags.value))

const dsForm = reactive({
  name: '', environment_id: null, db_type: 'mysql', host: 'mysql', port: 3306,
  database_name: '', username: '', password: '', allow_write: false,
  max_rows: 100, timeout_seconds: 10, is_default: false, is_enabled: true,
})

const dsDbLabel = computed(() => (dsForm.db_type === 'redis' ? 'DB Index' : '数据库'))
const dsDbPlaceholder = computed(() => (dsForm.db_type === 'redis' ? '0' : ''))
const dsPasswordPlaceholder = computed(() => {
  if (dsForm.db_type === 'redis') return dsEditingId.value ? '留空则不修改' : '无密码可留空'
  return dsEditingId.value ? (dsHasPassword.value ? '留空则不修改' : '请填写数据库密码') : '请填写数据库密码'
})
const dsWriteHint = computed(() => {
  if (dsForm.db_type === 'redis') return '允许写操作 (SET/DEL 等)'
  return '允许写操作 (INSERT/UPDATE/DELETE)'
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
      if (dsEditingId.value || dsForm.db_type === 'redis') {
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
  username: [{
    validator: (_rule, value, callback) => {
      if (dsForm.db_type === 'redis') {
        callback()
        return
      }
      if (!value?.trim()) {
        callback(new Error('请输入用户名'))
        return
      }
      callback()
    },
    trigger: 'blur',
  }],
}

function dbTypeLabel(t) {
  return { mysql: 'MySQL', postgresql: 'PostgreSQL', redis: 'Redis' }[(t || 'mysql').toLowerCase()] || t
}

function onDbTypeChange(type) {
  if (type === 'redis') {
    dsForm.port = 6379
    dsForm.database_name = dsForm.database_name || '0'
    dsForm.username = ''
  } else if (type === 'postgresql') {
    dsForm.port = 5432
  } else {
    dsForm.port = 3306
  }
}

async function loadFavorites() {
  try {
    const res = await dataFactoryApi.listFavorites({ project_id: projectId.value })
    const tags = new Set()
    for (const item of res.data || []) {
      if (item.item_type === 'tag') tags.add(item.item_key)
    }
    favoriteTags.value = tags
  } catch {
    favoriteTags.value = new Set()
  }
}

function isTagFavorited(tag) {
  return favoriteTags.value.has(tag)
}

function filterByFavoriteTag(tag) {
  recordKeyword.value = tag
  loadToolRecords()
}

async function toggleTagFavorite(tag) {
  try {
    if (isTagFavorited(tag)) {
      await dataFactoryApi.removeFavorite(projectId.value, { item_type: 'tag', item_key: tag })
      favoriteTags.value.delete(tag)
      ElMessage.success('已取消收藏')
    } else {
      await dataFactoryApi.addFavorite(projectId.value, { item_type: 'tag', item_key: tag })
      favoriteTags.value.add(tag)
      ElMessage.success('已收藏标签')
    }
    favoriteTags.value = new Set(favoriteTags.value)
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e.message || '操作失败')
  }
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

const recordEditVisible = ref(false)
const recordEditSaving = ref(false)
const recordEditForm = reactive({
  id: null,
  tagRef: '',
  tool_name: '',
  output_text: '',
  environment_id: null,
  remark: '',
})

function typeLabel(t) {
  return { setup: '前置', teardown: '后置', query: '查询' }[t] || t
}

function dfRef(tag) {
  return '${{df:' + tag + '}}'
}

async function loadToolRecords() {
  recordLoading.value = true
  try {
    const res = await dataFactoryApi.listToolRecords({
      project_id: projectId.value,
      environment_id: recordFilterEnvId.value || undefined,
      keyword: recordKeyword.value || undefined,
      size: 100,
    })
    toolRecordList.value = res.data?.list || []
  } finally {
    recordLoading.value = false
  }
}

function copyTagRef(tag) {
  const refStr = dfRef(tag)
  navigator.clipboard.writeText(refStr).then(() => {
    ElMessage.success('已复制 ' + refStr)
  }).catch(() => ElMessage.error('复制失败'))
}

function openRecordEdit(row) {
  recordEditForm.id = row.id
  recordEditForm.tagRef = dfRef(row.tag)
  recordEditForm.tool_name = row.tool_name
  recordEditForm.output_text = row.output_text || ''
  recordEditForm.environment_id = row.environment_id ?? null
  recordEditForm.remark = row.remark || ''
  recordEditVisible.value = true
}

async function saveRecordEdit() {
  if (!recordEditForm.id) return
  recordEditSaving.value = true
  try {
    await dataFactoryApi.updateToolRecord(recordEditForm.id, {
      environment_id: recordEditForm.environment_id,
      remark: recordEditForm.remark,
    })
    ElMessage.success('已保存')
    recordEditVisible.value = false
    await loadToolRecords()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e.message || '保存失败')
  } finally {
    recordEditSaving.value = false
  }
}

function formatUsageLines(usages) {
  return (usages || [])
    .map((u) => `· ${u.resource_type_label || u.resource_type}：${u.resource_name}（${u.location}）`)
    .join('\n')
}

async function deleteRecord(row) {
  if (row.usage_count > 0) {
    await ElMessageBox.alert(
      `标签「${row.tag}」仍被 ${row.usage_count} 处引用，请先在下列位置移除 ${dfRef(row.tag)} 后再删除：\n\n${formatUsageLines(row.usages)}`,
      '无法删除',
      { type: 'warning', confirmButtonText: '知道了' }
    )
    return
  }
  await ElMessageBox.confirm(`确定删除标签「${row.tag}」的记录？删除后 ${dfRef(row.tag)} 将无法再注入。`, '提示', { type: 'warning' })
  try {
    await dataFactoryApi.deleteToolRecord(row.id)
    ElMessage.success('已删除')
    loadToolRecords()
  } catch (e) {
    const detail = e?.response?.data?.detail
    if (e?.response?.status === 409 && detail?.usages) {
      await ElMessageBox.alert(
        `${detail.message || '仍被引用'}\n\n${formatUsageLines(detail.usages)}`,
        '无法删除',
        { type: 'warning' }
      )
      loadToolRecords()
      return
    }
    ElMessage.error(detail?.message || detail || e.message || '删除失败')
  }
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
    name: '', environment_id: proStore.envList[0]?.id || null, db_type: 'mysql', host: 'mysql', port: 3306,
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
      name: row.name, environment_id: row.environment_id, db_type: row.db_type || 'mysql',
      host: row.host, port: row.port,
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
  if (dsForm.db_type !== 'redis' && !dsEditingId.value && !dsForm.password?.trim()) {
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
  if (dsForm.db_type !== 'redis' && !dsEditingId.value && !pwd) {
    ElMessage.warning('请填写数据库密码')
    return
  }
  if (dsForm.db_type !== 'redis' && dsEditingId.value && !pwd && !dsHasPassword.value) {
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
  await loadFavorites()
  if (!proStore.envList?.length) await proStore.getEnvList(projectId.value)
  await loadToolRecords()
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
.usage-line {
  margin: 0 0 6px;
  font-size: 13px;
  line-height: 1.4;
}
.usage-loc {
  color: var(--el-text-color-secondary);
}
.favorites-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  padding: 8px 10px;
  background: #fdf6ec;
  border-radius: 4px;
}
.favorites-label {
  font-size: 12px;
  color: #e6a23c;
  font-weight: 500;
}
.fav-tag { cursor: pointer; }
.field-hint {
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}
</style>
