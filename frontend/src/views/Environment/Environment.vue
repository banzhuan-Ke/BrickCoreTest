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

  <el-dialog v-model="dialogVisible" :title="title" width="800px" center destroy-on-close @closed="onDialogClosed">
    <el-form :model="addEnvForm" label-width="108px" :rules="formDataRules" ref="formDataRef" class="env-form">
      <el-form-item label="环境名称" prop="name">
        <el-input v-model="addEnvForm.name" placeholder="如：测试环境、预发环境"/>
      </el-form-item>
      <el-form-item label="创建人" prop="username">
        <el-input v-model="addEnvForm.username" disabled/>
      </el-form-item>
      <el-form-item label="Base_url" prop="host">
        <el-input v-model="addEnvForm.host" placeholder="https://api.example.com"/>
        <div class="field-hint">保存前可点「校验」确认变量格式；引用语法 <code v-pre>${{变量名}}</code></div>
      </el-form-item>
      <el-form-item label="默认起始 URL">
        <el-input
          v-model="addEnvForm.default_start_url"
          placeholder="https://app.example.com/login"
          clearable
        />
        <div class="field-hint">Web 录制 / 交互调试预填；优先于项目默认，低于用例步骤中的 open_url</div>
      </el-form-item>

      <el-collapse v-model="uiStrategyActive" class="ui-strategy-collapse">
        <el-collapse-item name="strategy">
          <template #title>
            <span class="ui-strategy-panel__title">Web 慢站执行策略</span>
          </template>
          <div class="ui-strategy-panel">
            <div class="ui-strategy-panel__desc">
              只影响本环境的 Web UI 执行。慢站先调：
              <strong>超时倍率 2～3</strong>、导航选 <strong>DOM 就绪</strong>、需要时开
              <strong>操作后沉降 3000～8000</strong>、计划并发 1。
              下方「忙碌 / 就绪选择器」为选填进阶项，不会填可留空。
            </div>

            <div class="ui-strategy-grid">
              <el-form-item label="超时倍率" class="ui-strategy-grid__item">
                <el-input-number
                  v-model="addEnvForm.ui_timeout_scale"
                  :min="0.5"
                  :max="5"
                  :step="0.5"
                  :precision="1"
                  controls-position="right"
                />
                <div class="field-hint">把「未手工改过」的步骤超时整体放大；默认 1。慢站建议 2～3</div>
              </el-form-item>
              <el-form-item label="导航等待" class="ui-strategy-grid__item">
                <el-select v-model="addEnvForm.ui_nav_wait_until" style="width: 100%">
                  <el-option label="DOM 就绪（推荐）" value="domcontentloaded" />
                  <el-option label="页面加载完成" value="load" />
                  <el-option label="网络空闲（易卡住）" value="networkidle" />
                  <el-option label="尽早返回" value="commit" />
                </el-select>
                <div class="field-hint">
                  打开/刷新页面时等多久再继续。有长连接、轮询的页面请选「DOM 就绪」，不要选「页面加载完成」
                </div>
              </el-form-item>
            </div>

            <div class="ui-strategy-grid">
              <el-form-item label="操作后沉降" class="ui-strategy-grid__item">
                <div class="ui-strategy-inline">
                  <el-input-number
                    v-model="addEnvForm.ui_action_settle_ms"
                    :min="0"
                    :max="30000"
                    :step="500"
                    controls-position="right"
                  />
                  <span class="ui-strategy-inline__unit">ms</span>
                </div>
                <div class="field-hint">
                  点击/导航后等页面消停再继续（DOM 静默则提前结束）。默认 0。慢站点菜单再点子按钮建议 3000～8000
                </div>
              </el-form-item>
              <el-form-item label="静默窗口" class="ui-strategy-grid__item">
                <div class="ui-strategy-inline">
                  <el-input-number
                    v-model="addEnvForm.ui_action_settle_quiet_ms"
                    :min="0"
                    :max="5000"
                    :step="100"
                    controls-position="right"
                  />
                  <span class="ui-strategy-inline__unit">ms</span>
                </div>
                <div class="field-hint">
                  仅在「操作后沉降」&gt; 0 时生效：连续这么久无 DOM 变动即结束。默认 300；填 0 则空等满沉降预算
                </div>
              </el-form-item>
            </div>

            <el-form-item label="忙碌选择器">
              <el-input
                v-model="addEnvForm.ui_busy_selectors_text"
                type="textarea"
                :rows="2"
                placeholder="选填。示例：&#10;.el-loading-mask&#10;.ant-spin-spinning"
              />
              <div class="field-hint">
                <strong>选填。</strong>页面有转圈/半透明遮罩时才需要填（需开发协助从页面找 CSS）。
                填了之后：点击、输入前会先等遮罩消失。普通人不会写可直接留空——不填不会拖垮执行，只是遇 loading 时可能点早一点。
              </div>
            </el-form-item>

            <el-form-item label="遮罩探测">
              <div class="ui-strategy-inline">
                <el-input-number
                  v-model="addEnvForm.ui_busy_appear_probe_ms"
                  :min="0"
                  :max="5000"
                  :step="100"
                  controls-position="right"
                />
                <span class="ui-strategy-inline__unit">ms</span>
              </div>
              <div class="field-hint">
                仅在已配置「忙碌选择器」时有用：点击后短等遮罩出现再消失。未配忙碌选择器时此项基本无效果。
              </div>
            </el-form-item>

            <el-form-item label="就绪选择器">
              <el-input
                v-model="addEnvForm.ui_ready_selector"
                placeholder="选填。示例：.main-content"
                clearable
              />
              <div class="field-hint">
                <strong>选填。</strong>打开页面后，再等某个业务区域出现（只填一个 CSS）。
                不会写就留空即可；留空时导航仍按上面的「导航等待」结束，不会额外等就绪点。
              </div>
            </el-form-item>

            <el-form-item label="就绪重试">
              <el-input-number
                v-model="addEnvForm.ui_readiness_retry"
                :min="0"
                :max="3"
                :step="1"
                controls-position="right"
              />
              <div class="field-hint">
                仅当「忙碌遮罩 / 就绪选择器」等待超时时，再多等几轮（不重跑打开页面或点击）。
                默认 0（不等待重试）。与步骤/用例失败重跑、套件计划无关，不会叠乘冲突。
              </div>
            </el-form-item>
          </div>
        </el-collapse-item>
      </el-collapse>

      <el-collapse v-model="uiAuthActive" class="ui-strategy-collapse">
        <el-collapse-item name="auth">
          <template #title>
            <span class="ui-strategy-panel__title">Web 启动登录态注入</span>
          </template>
          <div class="ui-strategy-panel">
            <div class="ui-strategy-panel__desc">
              打开 / 重置浏览器上下文时自动注入 Cookie、请求头或 LocalStorage（免重复登录 UI）。
              值支持 <code v-pre>${{token}}</code>。与「登录步骤片段」、接口 Token 授权可配合；不替代测试环境免登录运维方案。
            </div>
            <el-form-item label="启用注入">
              <el-switch v-model="addEnvForm.ui_auth_enabled" />
            </el-form-item>
            <template v-if="addEnvForm.ui_auth_enabled">
              <el-form-item label="Authorization">
                <el-input
                  v-model="addEnvForm.ui_auth_authorization"
                  placeholder="Bearer ${{token}}"
                  clearable
                />
                <div class="field-hint">写入浏览器请求头 Authorization；也可填完整头值</div>
              </el-form-item>

              <el-form-item label="LocalStorage">
                <div class="auth-kv-list">
                  <div
                    v-for="(row, idx) in addEnvForm.ui_auth_local_storage"
                    :key="'ls-' + idx"
                    class="auth-kv-row"
                  >
                    <el-input v-model="row.key" placeholder="键名，如 token" />
                    <el-input v-model="row.value" placeholder="值，如 ${{token}}" />
                    <el-button
                      type="danger"
                      link
                      :disabled="addEnvForm.ui_auth_local_storage.length <= 1"
                      @click="removeAuthLocalRow(idx)"
                    >删</el-button>
                  </div>
                  <el-button type="primary" link @click="addAuthLocalRow">添加一行</el-button>
                </div>
                <div class="field-hint">通过 init_script 在每次导航前写入；须与业务页同源</div>
              </el-form-item>

              <el-form-item label="Cookie">
                <div class="auth-kv-list">
                  <div
                    v-for="(row, idx) in addEnvForm.ui_auth_cookies"
                    :key="'ck-' + idx"
                    class="auth-cookie-row"
                  >
                    <el-input v-model="row.name" placeholder="name" />
                    <el-input v-model="row.value" placeholder="value / ${{sid}}" />
                    <el-input v-model="row.domain" placeholder="domain，如 .example.com" />
                    <el-input v-model="row.url" placeholder="或 url，如 https://app.example.com/" />
                    <el-button
                      type="danger"
                      link
                      :disabled="addEnvForm.ui_auth_cookies.length <= 1"
                      @click="removeAuthCookieRow(idx)"
                    >删</el-button>
                  </div>
                  <el-button type="primary" link @click="addAuthCookieRow">添加 Cookie</el-button>
                </div>
                <div class="field-hint">每条须填 domain 或 url 之一</div>
              </el-form-item>

              <el-form-item label="storage_state">
                <el-input
                  v-model="addEnvForm.ui_storage_state_text"
                  type="textarea"
                  :rows="3"
                  placeholder="执行机本机路径，如 D:\auth\state.json；或粘贴 Playwright storage_state JSON"
                />
                <div class="field-hint">可用用例步骤「导出登录态」生成文件后再填路径</div>
              </el-form-item>
            </template>
          </div>
        </el-collapse-item>
      </el-collapse>

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
  getEnvUiActionSettleMs,
  getEnvUiActionSettleQuietMs,
  getEnvUiAuthInjectForm,
  getEnvUiBusyAppearProbeMs,
  getEnvUiBusySelectorsText,
  getEnvUiNavWaitUntil,
  getEnvUiReadySelector,
  getEnvUiReadinessRetry,
  getEnvUiTimeoutScale,
  globalVarsForEditor,
  mergeEnvDefaultStartUrl,
  mergeEnvUiAuthInject,
  mergeEnvUiExecStrategy,
  validateDefaultStartUrl,
  DEFAULT_UI_ACTION_SETTLE_MS,
  DEFAULT_UI_ACTION_SETTLE_QUIET_MS,
  DEFAULT_UI_BUSY_APPEAR_PROBE_MS,
  DEFAULT_UI_NAV_WAIT_UNTIL,
  DEFAULT_UI_READINESS_RETRY,
  DEFAULT_UI_TIMEOUT_SCALE,
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
/** 慢站策略折叠：默认收起，点击标题展开 */
const uiStrategyActive = ref([])
/** 启动登录态折叠 */
const uiAuthActive = ref([])

function emptyAuthLocalRows() {
  return [{ key: '', value: '' }]
}
function emptyAuthCookieRows() {
  return [{ name: '', value: '', domain: '', path: '/', url: '' }]
}
function resetAuthFormFields() {
  addEnvForm.ui_auth_enabled = false
  addEnvForm.ui_auth_authorization = ''
  addEnvForm.ui_auth_local_storage = emptyAuthLocalRows()
  addEnvForm.ui_auth_cookies = emptyAuthCookieRows()
  addEnvForm.ui_storage_state_text = ''
}
function applyAuthFormFromEnv(globalVars) {
  const form = getEnvUiAuthInjectForm(globalVars)
  addEnvForm.ui_auth_enabled = form.enabled
  addEnvForm.ui_auth_authorization = form.authorization
  addEnvForm.ui_auth_local_storage = form.localStorage
  addEnvForm.ui_auth_cookies = form.cookies
  addEnvForm.ui_storage_state_text = form.storageStateText
}
function addAuthLocalRow() {
  addEnvForm.ui_auth_local_storage.push({ key: '', value: '' })
}
function removeAuthLocalRow(idx) {
  if (addEnvForm.ui_auth_local_storage.length <= 1) return
  addEnvForm.ui_auth_local_storage.splice(idx, 1)
}
function addAuthCookieRow() {
  addEnvForm.ui_auth_cookies.push({ name: '', value: '', domain: '', path: '/', url: '' })
}
function removeAuthCookieRow(idx) {
  if (addEnvForm.ui_auth_cookies.length <= 1) return
  addEnvForm.ui_auth_cookies.splice(idx, 1)
}

const addEnvForm = reactive({
  project_id: proStore.projectInfo.id,
  name: '测试环境',
  username: uStore.userInfo.username,
  host: 'http://',
  default_start_url: '',
  ui_timeout_scale: DEFAULT_UI_TIMEOUT_SCALE,
  ui_nav_wait_until: DEFAULT_UI_NAV_WAIT_UNTIL,
  ui_action_settle_ms: DEFAULT_UI_ACTION_SETTLE_MS,
  ui_action_settle_quiet_ms: DEFAULT_UI_ACTION_SETTLE_QUIET_MS,
  ui_busy_selectors_text: '',
  ui_busy_appear_probe_ms: DEFAULT_UI_BUSY_APPEAR_PROBE_MS,
  ui_ready_selector: '',
  ui_readiness_retry: DEFAULT_UI_READINESS_RETRY,
  ui_auth_enabled: false,
  ui_auth_authorization: '',
  ui_auth_local_storage: emptyAuthLocalRows(),
  ui_auth_cookies: emptyAuthCookieRows(),
  ui_storage_state_text: '',
  global_vars: {},
  default_headers: [],
})

const ClickAdd = () => {
  title.value = '新增环境'
  dialogVisible.value = true
  uiStrategyActive.value = []
  uiAuthActive.value = []
  addEnvForm.project_id = proStore.projectInfo?.id
  addEnvForm.name = '测试环境'
  addEnvForm.username = uStore.userInfo.username
  addEnvForm.host = 'http://'
  addEnvForm.default_start_url = ''
  addEnvForm.ui_timeout_scale = DEFAULT_UI_TIMEOUT_SCALE
  addEnvForm.ui_nav_wait_until = DEFAULT_UI_NAV_WAIT_UNTIL
  addEnvForm.ui_action_settle_ms = DEFAULT_UI_ACTION_SETTLE_MS
  addEnvForm.ui_action_settle_quiet_ms = DEFAULT_UI_ACTION_SETTLE_QUIET_MS
  addEnvForm.ui_busy_selectors_text = ''
  addEnvForm.ui_busy_appear_probe_ms = DEFAULT_UI_BUSY_APPEAR_PROBE_MS
  addEnvForm.ui_ready_selector = ''
  addEnvForm.ui_readiness_retry = DEFAULT_UI_READINESS_RETRY
  resetAuthFormFields()
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
  const {
    default_start_url,
    ui_timeout_scale,
    ui_nav_wait_until,
    ui_action_settle_ms,
    ui_action_settle_quiet_ms,
    ui_busy_selectors_text,
    ui_busy_appear_probe_ms,
    ui_ready_selector,
    ui_readiness_retry,
    ui_auth_enabled,
    ui_auth_authorization,
    ui_auth_local_storage,
    ui_auth_cookies,
    ui_storage_state_text,
    ...rest
  } = addEnvForm
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
  const strategy = mergeEnvUiExecStrategy(globalVars, {
    timeoutScale: ui_timeout_scale,
    navWaitUntil: ui_nav_wait_until,
    busySelectorsText: ui_busy_selectors_text,
    readySelector: ui_ready_selector,
    readinessRetry: ui_readiness_retry,
    busyAppearProbeMs: ui_busy_appear_probe_ms,
    actionSettleMs: ui_action_settle_ms,
    actionSettleQuietMs: ui_action_settle_quiet_ms,
  })
  if (!strategy.ok) {
    ElMessage.error(strategy.error)
    return null
  }
  const auth = mergeEnvUiAuthInject(strategy.globalVars, {
    enabled: ui_auth_enabled,
    authorization: ui_auth_authorization,
    localStorage: ui_auth_local_storage,
    cookies: ui_auth_cookies,
    storageStateText: ui_storage_state_text,
  })
  if (!auth.ok) {
    ElMessage.error(auth.error)
    return null
  }
  return {
    ...rest,
    global_vars: auth.globalVars,
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
  uiStrategyActive.value = []
  uiAuthActive.value = []
  addEnvForm.id = env.id
  addEnvForm.name = env.name
  addEnvForm.username = env.username
  addEnvForm.host = env.host
  addEnvForm.default_start_url = getEnvDefaultStartUrl(env.global_vars)
  addEnvForm.ui_timeout_scale = getEnvUiTimeoutScale(env.global_vars)
  addEnvForm.ui_nav_wait_until = getEnvUiNavWaitUntil(env.global_vars)
  addEnvForm.ui_action_settle_ms = getEnvUiActionSettleMs(env.global_vars)
  addEnvForm.ui_action_settle_quiet_ms = getEnvUiActionSettleQuietMs(env.global_vars)
  addEnvForm.ui_busy_selectors_text = getEnvUiBusySelectorsText(env.global_vars)
  addEnvForm.ui_busy_appear_probe_ms = getEnvUiBusyAppearProbeMs(env.global_vars)
  addEnvForm.ui_ready_selector = getEnvUiReadySelector(env.global_vars)
  addEnvForm.ui_readiness_retry = getEnvUiReadinessRetry(env.global_vars)
  applyAuthFormFromEnv(env.global_vars)
  addEnvForm.global_vars = globalVarsForEditor(
    env.global_vars && typeof env.global_vars === 'object' ? { ...env.global_vars } : {}
  )
  addEnvForm.default_headers = Array.isArray(env.default_headers) ? env.default_headers.map((h) => ({ ...h })) : []
}

const clickCopy = (env) => {
  title.value = '复制环境'
  dialogVisible.value = true
  uiStrategyActive.value = []
  uiAuthActive.value = []
  delete addEnvForm.id
  addEnvForm.project_id = proStore.projectInfo?.id || env.project_id
  addEnvForm.name = suggestCopyName(env.name)
  addEnvForm.username = uStore.userInfo.username
  addEnvForm.host = env.host
  addEnvForm.default_start_url = getEnvDefaultStartUrl(env.global_vars)
  addEnvForm.ui_timeout_scale = getEnvUiTimeoutScale(env.global_vars)
  addEnvForm.ui_nav_wait_until = getEnvUiNavWaitUntil(env.global_vars)
  addEnvForm.ui_action_settle_ms = getEnvUiActionSettleMs(env.global_vars)
  addEnvForm.ui_action_settle_quiet_ms = getEnvUiActionSettleQuietMs(env.global_vars)
  addEnvForm.ui_busy_selectors_text = getEnvUiBusySelectorsText(env.global_vars)
  addEnvForm.ui_busy_appear_probe_ms = getEnvUiBusyAppearProbeMs(env.global_vars)
  addEnvForm.ui_ready_selector = getEnvUiReadySelector(env.global_vars)
  addEnvForm.ui_readiness_retry = getEnvUiReadinessRetry(env.global_vars)
  applyAuthFormFromEnv(env.global_vars)
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
  addEnvForm.ui_timeout_scale = DEFAULT_UI_TIMEOUT_SCALE
  addEnvForm.ui_nav_wait_until = DEFAULT_UI_NAV_WAIT_UNTIL
  addEnvForm.ui_action_settle_ms = DEFAULT_UI_ACTION_SETTLE_MS
  addEnvForm.ui_action_settle_quiet_ms = DEFAULT_UI_ACTION_SETTLE_QUIET_MS
  addEnvForm.ui_busy_selectors_text = ''
  addEnvForm.ui_busy_appear_probe_ms = DEFAULT_UI_BUSY_APPEAR_PROBE_MS
  addEnvForm.ui_ready_selector = ''
  addEnvForm.ui_readiness_retry = DEFAULT_UI_READINESS_RETRY
  resetAuthFormFields()
  uiAuthActive.value = []
  addEnvForm.global_vars = {}
  addEnvForm.default_headers = []
}
</script>

<style scoped>
.field-hint {
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.55;
}

.field-hint code {
  background: var(--el-fill-color);
  padding: 1px 4px;
  border-radius: 3px;
  font-size: 11px;
}

.field-hint strong {
  color: var(--el-text-color-regular);
  font-weight: 600;
}

.env-form :deep(.el-form-item) {
  margin-bottom: 16px;
}

.ui-strategy-collapse {
  margin: 4px 0 20px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-fill-color-blank);
  overflow: hidden;
}

.ui-strategy-collapse :deep(.el-collapse-item__header) {
  height: auto;
  min-height: 44px;
  line-height: 1.4;
  padding: 10px 14px;
  border-bottom: none;
  background: transparent;
}

.ui-strategy-collapse :deep(.el-collapse-item__wrap) {
  border-bottom: none;
}

.ui-strategy-collapse :deep(.el-collapse-item__content) {
  padding: 0 14px 8px;
}

.ui-strategy-panel {
  margin: 0;
  padding: 0;
  border: none;
  border-radius: 0;
  background: transparent;
}

.ui-strategy-panel__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  line-height: 1.4;
}

.ui-strategy-panel__desc {
  margin: 0 0 12px;
  padding-bottom: 10px;
  border-bottom: 1px dashed var(--el-border-color-lighter);
  font-size: 12px;
  line-height: 1.6;
  color: var(--el-text-color-secondary);
}

.ui-strategy-panel__desc code {
  background: var(--el-fill-color);
  padding: 1px 4px;
  border-radius: 3px;
  font-size: 11px;
}

.ui-strategy-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 16px;
}

@media (max-width: 720px) {
  .ui-strategy-grid {
    grid-template-columns: 1fr;
  }
}

.ui-strategy-inline {
  display: flex;
  align-items: center;
  gap: 8px;
}

.ui-strategy-inline__unit {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.auth-kv-list {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.auth-kv-row {
  display: grid;
  grid-template-columns: 1fr 1.4fr auto;
  gap: 8px;
  align-items: center;
}

.auth-cookie-row {
  display: grid;
  grid-template-columns: 1fr 1fr 1.2fr 1.4fr auto;
  gap: 6px;
  align-items: center;
}

@media (max-width: 720px) {
  .auth-kv-row,
  .auth-cookie-row {
    grid-template-columns: 1fr;
  }
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
