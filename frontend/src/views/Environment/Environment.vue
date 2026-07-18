<template>
  <PageCard>
    <template #title>
      <el-button size="small" type="primary" icon="Plus" @click="ClickAdd">环境</el-button>
    </template>
    <template #main>
      <el-table :data="proStore.envList" :header-cell-style="{'text-align':'center'}"
                :cell-style="{'text-align':'center'}" stripe>
        <template #empty>
          <div class="table-empty">
            <div class="empty-icon">
              <el-icon :size="40" color="#909399"><OfficeBuilding /></el-icon>
            </div>
            <div>暂无数据</div>
          </div>
        </template>
        <el-table-column label="序号" type="index" width="90"></el-table-column>
        <el-table-column prop="name" label="环境名称" min-width="120"></el-table-column>
        <el-table-column prop="project" label="所属项目" min-width="100"/>
        <el-table-column prop="host" label="Base_url" show-overflow-tooltip min-width="200px"></el-table-column>
        <el-table-column label="环境变量" min-width="220">
          <template #default="scope">
            <el-tooltip :content="varsTooltip(scope.row.global_vars)" placement="top" :disabled="!varKeyCount(scope.row.global_vars)">
              <span class="vars-preview">{{ formatVarsPreview(scope.row.global_vars) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column prop="username" label="创建人" width="100"></el-table-column>
        <el-table-column prop="create_time" label="创建时间" min-width="160">
          <template #default="scope">
            {{ dateTools.rTime(scope.row.create_time) }}
          </template>
        </el-table-column>
        <el-table-column label="更新时间" min-width="160">
          <template #default="scope">
            {{ dateTools.rTime(scope.row.update_time) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="260" fixed="right">
          <template #default="scope">
            <div class="env-action-btns">
              <el-button size="small" type="primary" plain @click="clickEdit(scope.row)" icon="Edit">编辑</el-button>
              <el-button size="small" type="success" plain @click="clickCopy(scope.row)" icon="CopyDocument">复制</el-button>
              <el-button size="small" type="danger" plain @click="handleDelete(scope.row)" icon="Delete">删除</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </template>
  </PageCard>

  <el-dialog v-model="dialogVisible" :title="title" width="720px" center destroy-on-close @closed="onDialogClosed">
    <el-form :model="addEnvForm" label-width="100px" :rules="formDataRules" ref="formDataRef">
      <el-form-item label="环境名称" prop="name">
        <el-input v-model="addEnvForm.name" placeholder="如：测试环境、预发环境"/>
      </el-form-item>
      <el-form-item label="创建人" prop="username">
        <el-input v-model="addEnvForm.username" disabled/>
      </el-form-item>
      <el-form-item label="Base_url" prop="host">
        <el-input v-model="addEnvForm.host" placeholder="https://api.example.com"/>
        <div class="field-hint">保存前可点击「校验」确认变量格式；引用语法 <code v-pre>${{变量名}}</code></div>
      </el-form-item>
      <el-form-item label="默认起始 URL">
        <el-input
          v-model="addEnvForm.default_start_url"
          placeholder="https://app.example.com/login"
          clearable
        />
        <div class="field-hint">Web 录制 / 交互调试预填；优先于项目默认，低于用例步骤中的 open_url</div>
      </el-form-item>
      <el-form-item label="环境变量">
        <GlobalVarsEditor ref="globalVarsEditorRef" v-model="addEnvForm.global_vars" json-height="260px"/>
        <el-collapse class="env-tips-collapse">
          <el-collapse-item title="使用说明（变量引用、Faker、优先级）" name="tips">
            <div class="tip-content">
              <p><strong>引用：</strong>UI / 接口用例中写 <code v-pre>${{token}}</code>、<code v-pre>${{username}}</code></p>
              <p><strong>Faker：</strong>变量值可写 <code>faker.random_int(min=100,max=100000)</code>，或引用内置 <code v-pre>${{random_int}}</code></p>
              <p><strong>嵌套：</strong><code>{"tag_name": "标签_${{random_int}}"}</code>，用例里用 <code v-pre>${{tag_name}}</code></p>
              <p><strong>描述：</strong>填写用途说明，在用例/接口中「插入变量」与变量预览时可查看</p>
              <p><strong>敏感项：</strong>名称含 token/password 等会自动按密码框显示，可手动开关「敏感」列</p>
              <p><strong>优先级：</strong>用例提取/脚本变量 &gt; 动态缓存 &gt; 本页全局变量</p>
            </div>
          </el-collapse-item>
        </el-collapse>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false" plain>取消</el-button>
      <el-button v-if="title === '修改环境'" type="primary" @click="UpdateEnv(formDataRef)">确定</el-button>
      <el-button v-else type="primary" @click="addEnv(formDataRef)">{{ title === '复制环境' ? '创建副本' : '确定' }}</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { OfficeBuilding } from '@element-plus/icons-vue'
import { ProjectStore } from '@/stores/module/ProjectStore'
import http from '@/api/index'
import dateTools from '@/tools/dateTools'
import { ElMessage, ElMessageBox, ElNotification } from 'element-plus'
import PageCard from '@/components/PageCard.vue'
import GlobalVarsEditor from '@/components/GlobalVarsEditor.vue'
import { UserStore } from '@/stores/module/UserStore.js'
import { formatVarsPreview, validateVarsObject, countUserVars, userVarRows } from '@/utils/globalVars.js'
import {
  getEnvDefaultStartUrl,
  globalVarsForEditor,
  mergeEnvDefaultStartUrl,
  validateDefaultStartUrl,
} from '@/utils/caseDescription.js'

const uStore = UserStore()
const proStore = ProjectStore()
proStore.getEnvironmentList()

const globalVarsEditorRef = ref(null)

function varKeyCount(globalVars) {
  return countUserVars(globalVars)
}

function truncateText(text, max = 48) {
  const s = String(text || '').trim()
  if (!s || s.length <= max) return s
  return `${s.slice(0, max)}…`
}

function varsTooltip(globalVars) {
  const rows = userVarRows(globalVars)
  if (!rows.length) return ''
  return rows
    .map((r) => (r.description ? `${r.key}：${truncateText(r.description)}` : r.key))
    .join('\n')
}

const handleDelete = (row) => {
  ElMessageBox.confirm('此操作不可恢复，确认删除该环境吗？', '提示', {
    confirmButtonText: '确认',
    cancelButtonText: '取消',
    center: true,
    type: 'warning',
  })
    .then(async () => {
      const res = await http.environmentApi.deleteEnv(row.id)
      if (res.status === 204) {
        await proStore.getEnvironmentList()
        ElNotification({ title: '已成功删除该环境！', type: 'success', duration: 1500 })
      } else {
        ElNotification({ type: 'error', title: '删除失败！', duration: 1500, message: res.data.detail })
      }
    })
    .catch(() => {
      ElMessage({ type: 'info', message: '已取消删除操作。', duration: 1500 })
    })
}

let title = ref('修改环境')
const dialogVisible = ref(false)
const addEnvForm = reactive({
  project_id: proStore.projectInfo.id,
  name: '测试环境',
  username: uStore.userInfo.username,
  host: 'http://',
  default_start_url: '',
  global_vars: {},
  default_headers: [],
})

const ClickAdd = () => {
  title.value = '新增环境'
  dialogVisible.value = true
  addEnvForm.project_id = proStore.projectInfo?.id
  addEnvForm.name = '测试环境'
  addEnvForm.username = uStore.userInfo.username
  addEnvForm.host = 'http://'
  addEnvForm.default_start_url = ''
  addEnvForm.global_vars = {}
  addEnvForm.default_headers = []
}

const formDataRules = reactive({
  name: [{ required: true, message: '环境名称不能为空！', trigger: 'blur' }],
  host: [{ required: true, message: '环境 host 不能为空！', trigger: 'blur' }],
})

const formDataRef = ref()

function preparePayload() {
  const vars = globalVarsEditorRef.value?.validateAndGet?.()
  if (vars === null) return null
  const check = validateVarsObject(vars ?? addEnvForm.global_vars)
  if (!check.ok) {
    ElMessage.error(check.error)
    return null
  }
  const { default_start_url, ...rest } = addEnvForm
  const urlCheck = validateDefaultStartUrl(default_start_url)
  if (!urlCheck.ok) {
    ElMessage.error(urlCheck.error)
    return null
  }
  let globalVars
  try {
    globalVars = mergeEnvDefaultStartUrl(vars ?? addEnvForm.global_vars ?? {}, default_start_url)
  } catch (e) {
    ElMessage.error(e.message || '默认起始 URL 无效')
    return null
  }
  return {
    ...rest,
    global_vars: globalVars,
    project_id: proStore.projectInfo?.id || addEnvForm.project_id,
  }
}

async function addEnv(elForm) {
  elForm.validate(async (res) => {
    if (!res) return
    const data = preparePayload()
    if (!data) return
    const response = await http.environmentApi.createEnv(data)
    if (response.status === 201) {
      ElNotification({ type: 'success', title: '已成功创建环境！', duration: 1500 })
      await proStore.getEnvironmentList()
      dialogVisible.value = false
    } else {
      ElNotification({ type: 'error', title: '创建环境失败！', duration: 1500, message: response.data.detail })
    }
  })
}

function suggestCopyName(baseName) {
  const existing = new Set((proStore.envList || []).map((e) => e.name))
  let name = `${baseName}-副本`
  let suffix = 1
  while (existing.has(name)) {
    suffix += 1
    name = `${baseName}-副本${suffix}`
  }
  return name
}

const clickEdit = (env) => {
  title.value = '修改环境'
  dialogVisible.value = true
  addEnvForm.id = env.id
  addEnvForm.name = env.name
  addEnvForm.username = env.username
  addEnvForm.host = env.host
  addEnvForm.default_start_url = getEnvDefaultStartUrl(env.global_vars)
  addEnvForm.global_vars = globalVarsForEditor(
    env.global_vars && typeof env.global_vars === 'object' ? { ...env.global_vars } : {}
  )
  addEnvForm.default_headers = Array.isArray(env.default_headers) ? env.default_headers.map((h) => ({ ...h })) : []
}

const clickCopy = (env) => {
  title.value = '复制环境'
  dialogVisible.value = true
  delete addEnvForm.id
  addEnvForm.project_id = proStore.projectInfo?.id || env.project_id
  addEnvForm.name = suggestCopyName(env.name)
  addEnvForm.username = uStore.userInfo.username
  addEnvForm.host = env.host
  addEnvForm.default_start_url = getEnvDefaultStartUrl(env.global_vars)
  addEnvForm.global_vars = globalVarsForEditor(
    env.global_vars && typeof env.global_vars === 'object' ? JSON.parse(JSON.stringify(env.global_vars)) : {}
  )
  addEnvForm.default_headers = Array.isArray(env.default_headers)
    ? env.default_headers.map((h) => ({ ...h }))
    : []
}

async function UpdateEnv(elForm) {
  elForm.validate(async (res) => {
    if (!res) return
    const data = preparePayload()
    if (!data) return
    const response = await http.environmentApi.updateEnv(data.id, data)
    if (response.status === 200) {
      ElNotification({ type: 'success', title: '已成功修改环境！', duration: 1500 })
      await proStore.getEnvironmentList()
      dialogVisible.value = false
    } else {
      ElNotification({ type: 'error', title: '修改环境失败！', duration: 1500, message: response.data.detail })
    }
  })
}

function onDialogClosed() {
  addEnvForm.default_start_url = ''
  addEnvForm.global_vars = {}
  addEnvForm.default_headers = []
}
</script>

<style scoped>
.field-hint {
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}

.field-hint code {
  background: var(--el-fill-color);
  padding: 1px 4px;
  border-radius: 3px;
  font-size: 11px;
}

.vars-preview {
  font-size: 12px;
  color: var(--el-text-color-regular);
}

.env-tips-collapse {
  margin-top: 12px;
  width: 100%;
}

.tip-content {
  font-size: 12px;
  line-height: 1.75;
  color: var(--el-text-color-regular);
}

.tip-content p {
  margin: 4px 0;
}

.tip-content code {
  background: var(--el-fill-color);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 11px;
}

.env-action-btns {
  display: inline-flex;
  flex-wrap: nowrap;
  align-items: center;
  justify-content: center;
  gap: 6px;
  white-space: nowrap;
}
</style>
