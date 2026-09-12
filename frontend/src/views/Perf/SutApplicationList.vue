<template>
  <PageCard>
    <template #title>
      <div style="font-size: 18px; font-weight: bold;">被测应用</div>
    </template>
    <template #main>
      <el-alert type="info" :closable="false" show-icon style="margin-bottom: 14px">
        <p style="margin: 0 0 8px">
          这里配置的是：<strong>压某个业务系统时，该看哪些装了被测监控采集器的机器</strong>。
          不负责采集；指标仍来自「被测服务器」上的被测监控采集器（各机同一套 CPU/内存，不会因应用不同而变）。
        </p>
        <p style="margin: 0 0 8px">
          <strong>怎么用：</strong>
          ① 新建业务系统名称 →
          ②「配机器」里选测试/预发等环境，把机器按分工挂上 →
          ③「预览机器」核对结果。
        </p>
        <p style="margin: 0">
          「机器分工」只是标签（如应用机 / 数据库），方便分组勾选；同一台机器可挂到多个业务系统（例如共享库）。
          压测报告自动带这些机器的曲线，需后续版本支持。
        </p>
      </el-alert>

      <el-alert
        v-if="!currentProjectId"
        type="warning"
        :closable="false"
        show-icon
        style="margin-bottom: 14px"
      >请先在顶部选择项目</el-alert>

      <div class="toolbar">
        <el-button type="primary" @click="fetchList" :icon="Refresh" :disabled="!currentProjectId">刷新</el-button>
        <el-button
          v-permission="'perf_scene:edit'"
          type="success"
          @click="openCreate"
          :disabled="!currentProjectId"
        >新建</el-button>
      </div>

      <el-table :data="tableData" v-loading="loading" stripe>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="name" label="业务系统" min-width="140" show-overflow-tooltip />
        <el-table-column label="机器分工" min-width="200">
          <template #default="{ row }">
            <el-tag
              v-for="r in row.roles || []"
              :key="r"
              size="small"
              style="margin-right: 4px"
            >{{ r }}</el-tag>
            <span v-if="!(row.roles || []).length" style="color: #999">未预设（配机器时可再填）</span>
          </template>
        </el-table-column>
        <el-table-column prop="binding_count" label="已配环境数" width="110" align="center" />
        <el-table-column prop="remark" label="备注" min-width="120" show-overflow-tooltip />
        <el-table-column label="操作" width="300" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openBindings(row)">配机器</el-button>
            <el-button link type="primary" size="small" @click="openResolve(row)">预览机器</el-button>
            <el-button
              v-permission="'perf_scene:edit'"
              link
              type="primary"
              size="small"
              @click="openEdit(row)"
            >编辑</el-button>
            <el-button
              v-permission="'perf_scene:edit'"
              link
              type="danger"
              size="small"
              @click="handleDelete(row)"
            >删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 新建/编辑 -->
      <el-dialog v-model="formVisible" :title="form.id ? '编辑业务系统' : '新建业务系统'" width="560px" destroy-on-close>
        <el-form :model="form" label-width="100px">
          <el-form-item label="名称" required>
            <el-input v-model="form.name" maxlength="100" placeholder="例如：订单系统、ESP 平台" />
          </el-form-item>
          <el-form-item label="机器分工">
            <el-select
              v-model="form.roles"
              multiple
              filterable
              allow-create
              default-first-option
              placeholder="可选。输入后回车，如 应用机 / 数据库 / mysql"
              style="width: 100%"
            />
            <div class="field-hint">
              预设本系统常见机器类型，方便下面「配机器」时按类型挂机。不填也可以，配机器时再写。
              这与采集器采哪些指标无关。
            </div>
          </el-form-item>
          <el-form-item label="备注">
            <el-input v-model="form.remark" type="textarea" :rows="2" maxlength="500" placeholder="可选" />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="formVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="saveForm">保存</el-button>
        </template>
      </el-dialog>

      <!-- 环境绑定 -->
      <el-dialog
        v-model="bindVisible"
        :title="`配机器 · ${bindApp?.name || ''}`"
        width="760px"
        destroy-on-close
      >
        <el-alert type="info" :closable="false" show-icon style="margin-bottom: 12px">
          选一个环境（测试 / 预发 / 生产等），说明「在这个环境下压该业务时，要看哪些被测服务器」。
          先到「被测服务器」菜单装好被测监控采集器、建好机器，再在这里勾选。
        </el-alert>
        <el-form label-width="100px">
          <el-form-item label="环境">
            <el-select v-model="bindEnvId" placeholder="选择环境" style="width: 100%" @change="onEnvChange">
              <el-option
                v-for="e in envList"
                :key="e.id"
                :label="e.name"
                :value="e.id"
              />
            </el-select>
          </el-form-item>
        </el-form>
        <div v-if="bindEnvId" class="bind-rows">
          <div class="bind-head">
            <span class="col-role">机器分工</span>
            <span class="col-servers">挂哪些被测服务器</span>
          </div>
          <div v-for="(row, idx) in bindRows" :key="idx" class="bind-row">
            <el-input
              v-model="row.role"
              placeholder="如 应用机 / 数据库"
              style="width: 140px"
              :disabled="!canEditBind"
            />
            <el-select
              v-model="row.server_ids"
              multiple
              filterable
              placeholder="勾选装了被测监控采集器的机器"
              style="flex: 1"
              :disabled="!canEditBind"
            >
              <el-option
                v-for="s in serverList"
                :key="s.id"
                :label="serverOptionLabel(s)"
                :value="s.id"
              />
            </el-select>
            <el-button v-if="canEditBind" link type="danger" @click="bindRows.splice(idx, 1)">删行</el-button>
          </div>
          <el-button v-if="canEditBind" size="small" @click="bindRows.push({ role: '', server_ids: [] })">
            再加一类机器
          </el-button>
        </div>
        <template #footer>
          <el-button
            v-if="bindEnvId"
            v-permission="'perf_scene:edit'"
            type="danger"
            plain
            @click="clearEnvBinding"
          >清空本环境配置</el-button>
          <el-button @click="bindVisible = false">关闭</el-button>
          <el-button
            v-permission="'perf_scene:edit'"
            type="primary"
            :loading="saving"
            :disabled="!bindEnvId"
            @click="saveBindings"
          >保存</el-button>
        </template>
      </el-dialog>

      <!-- 解析预览 -->
      <el-dialog v-model="resolveVisible" title="预览：压测时会带上哪些机器" width="720px" destroy-on-close>
        <el-alert type="info" :closable="false" show-icon style="margin-bottom: 12px">
          按上面「配机器」的结果汇总。后续压测报告会按此列表去取各机 CPU/内存曲线（功能尚未上线时，此处仅供核对）。
        </el-alert>
        <el-form label-width="88px">
          <el-form-item label="环境">
            <el-select v-model="resolveEnvId" placeholder="选择环境" style="width: 100%" @change="doResolve">
              <el-option v-for="e in envList" :key="e.id" :label="e.name" :value="e.id" />
            </el-select>
          </el-form-item>
        </el-form>
        <el-alert v-if="resolveResult?.error" type="warning" :closable="false" style="margin-bottom: 10px">
          {{ resolveErrorText(resolveResult.error) }}
        </el-alert>
        <el-alert
          v-else-if="(resolveResult?.missing_roles || []).length"
          type="info"
          :closable="false"
          style="margin-bottom: 10px"
        >
          业务系统预设了这些分工，但本环境还没挂机器：{{ resolveResult.missing_roles.join(', ') }}
        </el-alert>
        <p v-if="resolveResult && !resolveResult.error" class="resolve-summary">
          合计机器数：{{ (resolveResult.server_ids || []).length }}
          <span v-if="(resolveResult.server_ids || []).length">
            （ID：{{ resolveResult.server_ids.join(', ') }}）
          </span>
        </p>
        <el-table
          v-if="(resolveResult?.role_results || []).length"
          :data="resolveResult.role_results"
          size="small"
          border
          style="margin-bottom: 12px"
        >
          <el-table-column prop="role" label="机器分工" width="120" />
          <el-table-column label="状态" width="140">
            <template #default="{ row }">{{ roleStatusText(row.status) }}</template>
          </el-table-column>
          <el-table-column label="对应服务器">
            <template #default="{ row }">
              {{
                (row.servers || [])
                  .map((s) => `${s.name}(#${s.id})`)
                  .join(', ') || '—'
              }}
            </template>
          </el-table-column>
        </el-table>
        <el-table :data="resolveResult?.servers || []" size="small" border>
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column prop="name" label="被测服务器" />
          <el-table-column prop="hostname" label="主机名" />
          <el-table-column prop="role" label="服务器自带标签" width="120" />
          <el-table-column label="状态" width="120">
            <template #default="{ row }">{{ roleStatusText(row.status) }}</template>
          </el-table-column>
        </el-table>
      </el-dialog>
    </template>
  </PageCard>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import PageCard from '@/components/PageCard.vue'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { UserStore } from '@/stores/module/UserStore'
import { envApi } from '@/api/modules/sys'
import { perfSutApplicationApi, perfSutServerApi } from '@/api/modules/perf'

const proStore = ProjectStore()
const uStore = UserStore()
const loading = ref(false)
const saving = ref(false)
const tableData = ref([])
const formVisible = ref(false)
const form = reactive({ id: null, name: '', roles: [], remark: '' })

const bindVisible = ref(false)
const bindApp = ref(null)
const bindEnvId = ref(null)
const bindRows = ref([])
const existingBindings = ref([])
const envList = ref([])
const serverList = ref([])

const resolveVisible = ref(false)
const resolveAppId = ref(null)
const resolveEnvId = ref(null)
const resolveResult = ref(null)

const currentProjectId = computed(() => proStore.projectInfo?.id || null)
const canEditBind = computed(() => uStore.hasPermission('perf_scene:edit'))

const RESOLVE_ERR = {
  application_not_found: '业务系统不存在或已删除',
  env_not_found: '环境不存在或已删除',
  env_project_mismatch: '所选环境不属于当前项目',
  binding_not_found: '这个环境还没「配机器」，请先点配机器保存',
}

function resolveErrorText(code) {
  return RESOLVE_ERR[code] || code || ''
}

function roleStatusText(st) {
  const map = {
    ok: '可用',
    missing: '本环境未配置该类',
    unbound: '已写分工但未选机器',
    server_deleted: '机器已删除',
    server_project_mismatch: '机器不在本项目',
    monitoring_disabled: '监控已关',
    schedule_paused: '日程暂停采样',
    schedule_paused_will_force: '日常暂停，压测将强制采集',
    offline: '采集器离线',
  }
  return map[st] || st || '—'
}

function serverOptionLabel(s) {
  const bits = [s.name, `#${s.id}`]
  if (s.role) bits.push(s.role)
  bits.push(s.status === 'online' ? '在线' : '离线')
  if (!s.monitoring_enabled) bits.push('监控关')
  else if (s.sample_allowed === false) bits.push('日程暂停')
  return bits.join(' · ')
}

function errDetail(e) {
  return e?.response?.data?.detail || e?.data?.detail || e?.message || null
}

let listLoadSeq = 0

async function fetchList() {
  const pid = currentProjectId.value
  if (!pid) {
    tableData.value = []
    return
  }
  const seq = ++listLoadSeq
  loading.value = true
  try {
    const res = await perfSutApplicationApi.getList({ project_id: pid })
    if (seq !== listLoadSeq) return
    const data = res?.data || res || {}
    tableData.value = data.data || []
  } catch (e) {
    if (seq !== listLoadSeq) return
    ElMessage.error(errDetail(e) || '加载失败')
  } finally {
    if (seq === listLoadSeq) loading.value = false
  }
}

async function loadEnvsAndServers() {
  const pid = currentProjectId.value
  if (!pid) return
  try {
    const [eRes, sRes] = await Promise.all([
      envApi.getList({ project_id: pid }),
      perfSutServerApi.getList({ project_id: pid }),
    ])
    const ed = eRes?.data || eRes || {}
    envList.value = Array.isArray(ed) ? ed : ed.data || []
    if (!Array.isArray(envList.value)) envList.value = []
    const sd = sRes?.data || sRes || {}
    serverList.value = sd.data || []
  } catch (e) {
    envList.value = []
    serverList.value = []
    ElMessage.error(errDetail(e) || '加载环境/服务器失败')
  }
}

function openCreate() {
  form.id = null
  form.name = ''
  form.roles = []
  form.remark = ''
  formVisible.value = true
}

function openEdit(row) {
  form.id = row.id
  form.name = row.name || ''
  form.roles = [...(row.roles || [])]
  form.remark = row.remark || ''
  formVisible.value = true
}

async function saveForm() {
  if (!form.name.trim()) {
    ElMessage.warning('请填写名称')
    return
  }
  saving.value = true
  try {
    const payload = {
      name: form.name.trim(),
      roles: form.roles,
      remark: form.remark,
    }
    if (form.id) {
      await perfSutApplicationApi.update(form.id, payload)
    } else {
      await perfSutApplicationApi.create({
        project_id: currentProjectId.value,
        ...payload,
      })
    }
    formVisible.value = false
    ElMessage.success('已保存')
    await fetchList()
  } catch (e) {
    ElMessage.error(errDetail(e) || '保存失败')
  } finally {
    saving.value = false
  }
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(
      `删除业务系统「${row.name}」？各环境下已配的机器关系也会删掉（被测服务器与历史曲线不受影响）。`,
      '确认删除',
      { type: 'warning' }
    )
  } catch {
    return
  }
  try {
    await perfSutApplicationApi.delete(row.id)
    ElMessage.success('已删除')
    await fetchList()
  } catch (e) {
    ElMessage.error(errDetail(e) || '删除失败')
  }
}

async function openBindings(row) {
  bindApp.value = row
  bindEnvId.value = null
  bindRows.value = []
  bindVisible.value = true
  await loadEnvsAndServers()
  try {
    const res = await perfSutApplicationApi.getEnvBindings(row.id)
    const data = res?.data || res || {}
    existingBindings.value = data.data || []
  } catch (e) {
    existingBindings.value = []
    ElMessage.error(errDetail(e) || '加载绑定失败')
  }
}

function onEnvChange(envId) {
  const found = existingBindings.value.find((b) => b.environment_id === envId)
  if (found && Array.isArray(found.bindings) && found.bindings.length) {
    bindRows.value = found.bindings.map((b) => ({
      role: b.role || '',
      server_ids: [...(b.server_ids || [])],
    }))
  } else {
    const roles = bindApp.value?.roles || []
    bindRows.value = roles.length
      ? roles.map((r) => ({ role: r, server_ids: [] }))
      : [{ role: '', server_ids: [] }]
  }
}

async function saveBindings() {
  if (!bindApp.value || !bindEnvId.value) return
  saving.value = true
  try {
    const bindings = bindRows.value
      .filter((r) => (r.role || '').trim())
      .map((r) => ({
        role: r.role.trim(),
        server_ids: r.server_ids || [],
      }))
    await perfSutApplicationApi.putEnvBinding(bindApp.value.id, {
      environment_id: bindEnvId.value,
      bindings,
    })
    ElMessage.success('已保存本环境的机器配置')
    const res = await perfSutApplicationApi.getEnvBindings(bindApp.value.id)
    const data = res?.data || res || {}
    existingBindings.value = data.data || []
    onEnvChange(bindEnvId.value)
    await fetchList()
  } catch (e) {
    ElMessage.error(errDetail(e) || '保存失败')
  } finally {
    saving.value = false
  }
}

async function clearEnvBinding() {
  if (!bindApp.value || !bindEnvId.value) return
  try {
    await ElMessageBox.confirm(
      '清空当前环境下已挂的机器？被测服务器本身不会删除。',
      '确认清空',
      { type: 'warning' }
    )
  } catch {
    return
  }
  try {
    await perfSutApplicationApi.deleteEnvBinding(bindApp.value.id, bindEnvId.value)
    ElMessage.success('已清空本环境配置')
    bindRows.value = []
    const res = await perfSutApplicationApi.getEnvBindings(bindApp.value.id)
    existingBindings.value = (res?.data || res || {}).data || []
    await fetchList()
  } catch (e) {
    ElMessage.error(errDetail(e) || '清空失败')
  }
}

async function openResolve(row) {
  resolveAppId.value = row.id
  resolveEnvId.value = null
  resolveResult.value = null
  resolveVisible.value = true
  await loadEnvsAndServers()
}

async function doResolve() {
  if (!resolveAppId.value || !resolveEnvId.value) return
  try {
    const res = await perfSutApplicationApi.resolve(resolveAppId.value, {
      environment_id: resolveEnvId.value,
    })
    resolveResult.value = res?.data || res || null
  } catch (e) {
    ElMessage.error(errDetail(e) || '预览失败')
  }
}

watch(
  () => proStore.projectInfo?.id,
  (id) => {
    if (id) fetchList()
    else tableData.value = []
  },
  { immediate: true }
)
</script>

<style scoped>
.toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
.field-hint {
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--el-text-color-secondary);
}
.bind-rows {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.bind-head {
  display: flex;
  gap: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  padding: 0 2px;
}
.bind-head .col-role {
  width: 140px;
}
.bind-head .col-servers {
  flex: 1;
}
.bind-row {
  display: flex;
  gap: 8px;
  align-items: center;
}
.resolve-summary {
  margin: 0 0 10px;
  font-size: 13px;
  color: var(--el-text-color-regular);
}
</style>
