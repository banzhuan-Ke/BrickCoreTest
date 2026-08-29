<template>
  <PageCard>
    <template #title>
      <div class="env-page-title">
        <el-tabs v-model="mainTab" class="env-main-tabs" @tab-change="onMainTabChange">
          <el-tab-pane label="环境列表" name="envs" />
          <el-tab-pane label="项目共享变量" name="project" />
        </el-tabs>
        <div v-if="mainTab === 'envs'" class="env-page-actions">
          <el-button size="small" @click="batchDialogVisible = true">同步变量</el-button>
          <el-button size="small" @click="openUsages()">查看引用</el-button>
          <el-button size="small" type="primary" icon="Plus" @click="ClickAdd">环境</el-button>
        </div>
        <div v-else class="env-page-actions">
          <el-button size="small" @click="openUsages()">查看引用</el-button>
          <el-button size="small" type="primary" :loading="projectVarsSaving" @click="saveProjectVars">
            保存项目变量
          </el-button>
        </div>
      </div>
    </template>
    <template #main>
      <div v-show="mainTab === 'envs'">
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
      </div>

      <div v-show="mainTab === 'project'" class="project-vars-pane">
        <el-alert type="info" :closable="false" show-icon class="project-vars-alert">
          各环境共用的默认值；与环境变量同名时以环境为准。账号密码等差异项请写在各环境。
          AI / 禅道 / 用例命名 / 知识库等系统配置不在此编辑（已自动隐藏），保存时不会被冲掉。
        </el-alert>
        <GlobalVarsEditor
          ref="projectVarsEditorRef"
          v-model="projectGlobalVars"
          json-height="360px"
          show-usages
          @view-usages="openUsages"
        />
      </div>
    </template>
  </PageCard>

  <EnvVarsBatchDialog
    v-model="batchDialogVisible"
    :project-id="proStore.projectInfo?.id"
    :env-list="proStore.envList"
    @done="proStore.getEnvironmentList()"
  />
  <VarUsagesDialog
    v-model="usagesDialogVisible"
    :project-id="proStore.projectInfo?.id"
    :var-name="usagesVarName"
    :quick-var-names="usagesQuickNames"
  />

  <el-dialog v-model="dialogVisible" :title="title" width="960px" center destroy-on-close @closed="onDialogClosed">
    <el-form :model="addEnvForm" label-width="130px" :rules="formDataRules" ref="formDataRef" class="env-form">
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
      <el-form-item label="默认接口执行机">
        <ViaWorkerSelect v-model="addEnvForm.default_perf_worker_id" variant="env" />
      </el-form-item>

      <el-collapse v-model="uiStrategyActive" class="ui-strategy-collapse">
        <el-collapse-item name="strategy">
          <template #title>
            <div class="ui-strategy-panel__title-row">
              <span class="ui-strategy-panel__title">Web 慢站执行策略</span>
              <el-tag size="small" type="info" effect="plain">可选</el-tag>
            </div>
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

      <el-collapse v-model="uiAuthActive" class="ui-strategy-collapse ui-auth-collapse">
        <el-collapse-item name="auth">
          <template #title>
            <div class="ui-strategy-panel__title-row">
              <span class="ui-strategy-panel__title">Web 启动登录态注入</span>
              <el-tag
                v-if="addEnvForm.ui_auth_enabled && authConfigCount > 0"
                size="small"
                type="success"
                effect="plain"
              >已启用 · {{ authConfigCount }} 项</el-tag>
              <el-tag
                v-else-if="!addEnvForm.ui_auth_enabled && authConfigCount > 0"
                size="small"
                type="info"
                effect="plain"
              >已停用 · 配置保留</el-tag>
              <el-tag v-else size="small" type="info" effect="plain">未配置</el-tag>
            </div>
          </template>
          <div class="ui-strategy-panel ui-auth-panel">
            <div class="ui-auth-panel__head">
              <div class="ui-auth-panel__switch">
                <span class="ui-auth-panel__switch-label">启用注入</span>
                <el-switch v-model="addEnvForm.ui_auth_enabled" />
                <span class="ui-auth-panel__switch-hint">
                  {{ addEnvForm.ui_auth_enabled ? '打开浏览器时自动注入' : '停用后仍保留下方配置，可随时再开' }}
                </span>
              </div>
              <p class="ui-auth-panel__desc">
                站点登录态可建多条：导入导出 json、解析后可改字段，启用项合并注入（换执行机无需本机路径）。
                与接口 Token 授权不同：不过期自动重登，也不会自动跳「登录后地址」。
              </p>
            </div>

            <el-alert
              v-if="!addEnvForm.ui_auth_enabled && authConfigCount > 0"
              type="info"
              :closable="false"
              show-icon
              class="ui-auth-panel__alert"
              title="当前已停用：保存后不会注入，配置不会清空"
            />

            <div class="ui-auth-section">
              <div class="ui-auth-section__title">站点登录态</div>
              <UiAuthProfilesEditor
                v-model="addEnvForm.ui_auth_profiles"
                v-model:legacy-path="addEnvForm.ui_auth_legacy_path"
              />
              <div class="field-hint">
                推荐：执行机「导出登录态」→ 此处导入 → 可改 Cookie / Storage。多站点各建一条并启用。
              </div>
            </div>

            <el-collapse class="ui-auth-extra">
              <el-collapse-item name="common">
                <template #title>
                  <span class="ui-auth-extra__title">公共注入（可选）</span>
                  <span class="ui-auth-extra__sub">Authorization / LocalStorage / SessionStorage / Cookie</span>
                </template>
                <el-form-item label="Authorization">
                  <el-input
                    v-model="addEnvForm.ui_auth_authorization"
                    placeholder="Bearer ${{token}}"
                    clearable
                  />
                  <div class="field-hint">写入浏览器请求头 Authorization</div>
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
                </el-form-item>

                <el-form-item label="SessionStorage">
                  <div class="auth-kv-list">
                    <div
                      v-for="(row, idx) in addEnvForm.ui_auth_session_storage"
                      :key="'ss-' + idx"
                      class="auth-kv-row"
                    >
                      <el-input v-model="row.key" placeholder="键名" />
                      <el-input v-model="row.value" placeholder="值 / ${{var}}" />
                      <el-button
                        type="danger"
                        link
                        :disabled="addEnvForm.ui_auth_session_storage.length <= 1"
                        @click="removeAuthSessionRow(idx)"
                      >删</el-button>
                    </div>
                    <el-button type="primary" link @click="addAuthSessionRow">添加一行</el-button>
                  </div>
                </el-form-item>

                <el-form-item label="Cookie">
                  <div class="auth-kv-list">
                    <div
                      v-for="(row, idx) in addEnvForm.ui_auth_cookies"
                      :key="'ck-' + idx"
                      class="auth-cookie-row"
                    >
                      <el-input v-model="row.name" placeholder="name" />
                      <el-input v-model="row.value" placeholder="value" />
                      <el-input v-model="row.domain" placeholder="domain" />
                      <el-input v-model="row.url" placeholder="或 url" />
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
              </el-collapse-item>
            </el-collapse>
          </div>
        </el-collapse-item>
      </el-collapse>

      <div class="env-vars-panel">
        <div class="env-vars-panel__head">
          <span class="ui-strategy-panel__title">环境变量</span>
        </div>
        <div class="env-vars-panel__body">
          <GlobalVarsEditor
            ref="globalVarsEditorRef"
            v-model="addEnvForm.global_vars"
            json-height="260px"
            show-usages
            @view-usages="openUsages"
          />
          <el-collapse class="env-tips-collapse">
            <el-collapse-item name="tips">
              <template #title>
                <span class="env-tips-collapse__title">使用说明（变量引用、Faker、优先级）</span>
              </template>
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
        </div>
      </div>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false" plain>取消</el-button>
      <el-button v-if="title === '修改环境'" type="primary" @click="UpdateEnv(formDataRef)">确定</el-button>
      <el-button v-else type="primary" @click="addEnv(formDataRef)">{{ title === '复制环境' ? '创建副本' : '确定' }}</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { OfficeBuilding } from '@element-plus/icons-vue'
import { ProjectStore } from '@/stores/module/ProjectStore'
import http from '@/api/index'
import dateTools from '@/tools/dateTools'
import { ElMessage, ElMessageBox, ElNotification } from 'element-plus'
import PageCard from '@/components/PageCard.vue'
import GlobalVarsEditor from '@/components/GlobalVarsEditor.vue'
import ViaWorkerSelect from '@/components/ViaWorkerSelect.vue'
import UiAuthProfilesEditor from '@/components/UiAuthProfilesEditor.vue'
import EnvVarsBatchDialog from '@/components/EnvVarsBatchDialog.vue'
import VarUsagesDialog from '@/components/VarUsagesDialog.vue'
import { UserStore } from '@/stores/module/UserStore.js'
import { formatVarsPreview, validateVarsObject, countUserVars, userVarRows, mergeUserVarsWithSystem } from '@/utils/globalVars.js'
import {
  getEnvDefaultPerfWorkerId,
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
  mergeEnvDefaultPerfWorkerId,
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

const mainTab = ref('envs')
const batchDialogVisible = ref(false)
const usagesDialogVisible = ref(false)
const usagesVarName = ref('')
const projectGlobalVars = ref({})
const projectVarsEditorRef = ref(null)
const projectVarsSaving = ref(false)

const usagesQuickNames = computed(() => {
  const names = []
  for (const r of userVarRows(projectGlobalVars.value)) names.push(r.key)
  for (const env of proStore.envList || []) {
    for (const r of userVarRows(env.global_vars)) names.push(r.key)
  }
  for (const r of userVarRows(addEnvForm.global_vars)) names.push(r.key)
  return [...new Set(names.filter(Boolean))]
})

async function loadProjectVars() {
  await proStore.refreshProjectGlobals()
  const gv = proStore.projectInfo?.global_vars
  projectGlobalVars.value =
    gv && typeof gv === 'object' && !Array.isArray(gv) ? { ...gv } : {}
}

async function onMainTabChange(name) {
  if (name === 'project') {
    await loadProjectVars()
  }
}

function openUsages(name = '') {
  usagesVarName.value = name || ''
  usagesDialogVisible.value = true
}

async function saveProjectVars() {
  const projectId = proStore.projectInfo?.id
  if (!projectId) {
    ElMessage.warning('请先选择项目')
    return
  }
  if (!uStore.hasPermission?.('project:edit')) {
    ElMessage.warning('保存项目共享变量需要「项目编辑」权限，且一般为项目经理及以上角色')
    return
  }
  const edited = projectVarsEditorRef.value?.validateAndGet?.()
  if (edited === null) return
  // validateAndGet 已合并系统配置；再兜底一次防冲掉
  const merged = mergeUserVarsWithSystem(edited, proStore.projectInfo?.global_vars || {})
  projectVarsSaving.value = true
  try {
    const res = await http.projectApi.updateProject(projectId, { global_vars: merged })
    if (res.status === 200) {
      ElNotification({ title: '项目共享变量已保存', type: 'success', duration: 1500 })
      await proStore.refreshProjectGlobals()
      await loadProjectVars()
    } else {
      ElNotification({
        type: 'error',
        title: '保存失败',
        message: res.data?.detail || '请稍后重试',
        duration: 2000,
      })
    }
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '保存失败')
  } finally {
    projectVarsSaving.value = false
  }
}

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
function emptyAuthSessionRows() {
  return [{ key: '', value: '' }]
}
function emptyAuthCookieRows() {
  return [{ name: '', value: '', domain: '', path: '/', url: '' }]
}
function resetAuthFormFields() {
  addEnvForm.ui_auth_enabled = false
  addEnvForm.ui_auth_authorization = ''
  addEnvForm.ui_auth_local_storage = emptyAuthLocalRows()
  addEnvForm.ui_auth_session_storage = emptyAuthSessionRows()
  addEnvForm.ui_auth_cookies = emptyAuthCookieRows()
  addEnvForm.ui_storage_state_text = ''
  addEnvForm.ui_auth_profiles = []
  addEnvForm.ui_auth_legacy_path = ''
}
function applyAuthFormFromEnv(globalVars) {
  const form = getEnvUiAuthInjectForm(globalVars)
  addEnvForm.ui_auth_enabled = form.enabled
  addEnvForm.ui_auth_authorization = form.authorization
  addEnvForm.ui_auth_local_storage = form.localStorage
  addEnvForm.ui_auth_session_storage = form.sessionStorage
  addEnvForm.ui_auth_cookies = form.cookies
  addEnvForm.ui_storage_state_text = form.storageStateText
  addEnvForm.ui_auth_profiles = form.profiles || []
  addEnvForm.ui_auth_legacy_path = form.legacyPath || ''
}
function addAuthLocalRow() {
  addEnvForm.ui_auth_local_storage.push({ key: '', value: '' })
}
function removeAuthLocalRow(idx) {
  if (addEnvForm.ui_auth_local_storage.length <= 1) return
  addEnvForm.ui_auth_local_storage.splice(idx, 1)
}
function addAuthSessionRow() {
  addEnvForm.ui_auth_session_storage.push({ key: '', value: '' })
}
function removeAuthSessionRow(idx) {
  if (addEnvForm.ui_auth_session_storage.length <= 1) return
  addEnvForm.ui_auth_session_storage.splice(idx, 1)
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
  default_perf_worker_id: null,
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
  ui_auth_session_storage: emptyAuthSessionRows(),
  ui_auth_cookies: emptyAuthCookieRows(),
  ui_storage_state_text: '',
  ui_auth_profiles: [],
  ui_auth_legacy_path: '',
  global_vars: {},
  default_headers: [],
})

const authConfigCount = computed(() => {
  const profiles = addEnvForm.ui_auth_profiles || []
  let n = profiles.length
  if (String(addEnvForm.ui_auth_authorization || '').trim()) n += 1
  if ((addEnvForm.ui_auth_local_storage || []).some((r) => r.key)) n += 1
  if ((addEnvForm.ui_auth_session_storage || []).some((r) => r.key)) n += 1
  if ((addEnvForm.ui_auth_cookies || []).some((r) => r.name)) n += 1
  if (String(addEnvForm.ui_auth_legacy_path || '').trim()) n += 1
  return n
})

const ClickAdd = () => {
  title.value = '新增环境'
  dialogVisible.value = true
  uiStrategyActive.value = []
  uiAuthActive.value = []
  delete addEnvForm.id
  addEnvForm.project_id = proStore.projectInfo?.id
  addEnvForm.name = '测试环境'
  addEnvForm.username = uStore.userInfo.username
  addEnvForm.host = 'http://'
  addEnvForm.default_start_url = ''
  addEnvForm.default_perf_worker_id = null
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
    default_perf_worker_id,
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
    ui_auth_session_storage,
    ui_auth_cookies,
    ui_storage_state_text,
    ui_auth_profiles,
    ui_auth_legacy_path,
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
    globalVars = mergeEnvDefaultPerfWorkerId(globalVars, default_perf_worker_id)
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
    sessionStorage: ui_auth_session_storage,
    cookies: ui_auth_cookies,
    storageStateText: ui_storage_state_text,
    profiles: ui_auth_profiles,
    legacyPath: ui_auth_legacy_path,
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
  addEnvForm.default_perf_worker_id = getEnvDefaultPerfWorkerId(env.global_vars)
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
  addEnvForm.default_perf_worker_id = getEnvDefaultPerfWorkerId(env.global_vars)
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
  delete addEnvForm.id
  addEnvForm.default_start_url = ''
  addEnvForm.default_perf_worker_id = null
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

.env-form :deep(.el-form-item__label) {
  white-space: nowrap;
}

.env-form {
  padding: 0 4px;
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

.ui-strategy-panel__title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  width: 100%;
  padding-right: 8px;
}

.ui-auth-collapse :deep(.el-collapse-item__header) {
  background: linear-gradient(180deg, var(--el-fill-color-blank) 0%, var(--el-fill-color-lighter) 100%);
}

.ui-auth-panel__head {
  margin-bottom: 12px;
}

.ui-auth-panel__switch {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 8px;
}

.ui-auth-panel__switch-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.ui-auth-panel__switch-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.ui-auth-panel__desc {
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--el-text-color-secondary);
}

.ui-auth-panel__alert {
  margin-bottom: 12px;
}

.ui-auth-section {
  padding: 12px;
  margin-bottom: 10px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-bg-color);
}

.ui-auth-section__title {
  margin-bottom: 10px;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.ui-auth-extra {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  overflow: hidden;
}

.ui-auth-extra :deep(.el-collapse-item__header) {
  height: auto;
  min-height: 40px;
  padding: 8px 12px;
  background: var(--el-fill-color-lighter);
}

.ui-auth-extra :deep(.el-collapse-item__wrap) {
  border-top: 1px solid var(--el-border-color-extra-light);
}

.ui-auth-extra :deep(.el-collapse-item__content) {
  padding: 12px 12px 4px;
}

.ui-auth-extra__title {
  font-size: 13px;
  font-weight: 600;
  margin-right: 8px;
}

.ui-auth-extra__sub {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  font-weight: 400;
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

.env-vars-panel {
  margin: 4px 0 8px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-fill-color-blank);
  overflow: hidden;
}

.env-vars-panel__head {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 44px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--el-border-color-extra-light);
  background: linear-gradient(180deg, var(--el-fill-color-blank) 0%, var(--el-fill-color-lighter) 100%);
}

.env-vars-panel__body {
  padding: 14px 16px 12px;
}

.env-vars-panel__body :deep(.el-table) {
  width: 100%;
}

.env-vars-panel__body :deep(.el-table .el-table__cell) {
  padding: 8px 12px;
}

.env-vars-panel__body :deep(.el-table th.el-table__cell) {
  background: var(--el-fill-color-lighter);
  font-weight: 600;
}

.env-tips-collapse {
  margin-top: 12px;
  width: 100%;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  overflow: hidden;
}

.env-tips-collapse :deep(.el-collapse-item__header) {
  height: auto;
  min-height: 40px;
  line-height: 1.4;
  padding: 8px 14px;
  border-bottom: none;
  background: var(--el-fill-color-lighter);
}

.env-tips-collapse :deep(.el-collapse-item__wrap) {
  border-bottom: none;
}

.env-tips-collapse :deep(.el-collapse-item__content) {
  padding: 8px 14px 12px;
}

.env-tips-collapse__title {
  font-size: 13px;
  color: var(--el-text-color-regular);
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

.env-page-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  flex-wrap: wrap;
}

.env-main-tabs {
  flex: 1;
  min-width: 240px;
}

.env-main-tabs :deep(.el-tabs__header) {
  margin: 0;
}

.env-main-tabs :deep(.el-tabs__nav-wrap::after) {
  display: none;
}

.env-page-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.project-vars-pane {
  max-width: 960px;
}

.project-vars-alert {
  margin-bottom: 14px;
}
</style>
