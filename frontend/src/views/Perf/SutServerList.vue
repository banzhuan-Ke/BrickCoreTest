<template>
  <PageCard>
    <template #title>
      <div style="font-size: 18px; font-weight: bold;">被测服务器</div>
    </template>
    <template #main>
      <el-alert type="info" :closable="false" show-icon style="margin-bottom: 14px">
        在<strong>被测机 / 演示机宿主机</strong>安装被测监控采集器，回传 CPU/内存等主机指标。不要装在压测施压机上。
        Token 仅在创建/轮换时显示一次，请写入采集器配置文件，勿放 URL。
        平台侧指标默认保留约 <strong>14 天</strong>（项目设置「压测 AI → 指标保留天数」可覆盖；环境变量 <code>SUT_METRICS_RETAIN_DAYS</code>）；
        采集器本机缓冲默认 <code>buffer_hours=48</code>（约 2 天，仅断网补传）；采样间隔/上报间隔/本机缓冲可在本页「采集参数」修改，约 30 秒内心跳生效，无需登录被测机。
        报告/AI 会对比<strong>施压前基线</strong>与<strong>施压中</strong>资源摘要（需压测开始前采集器已在上报）。
      </el-alert>

      <el-alert
        v-if="!currentProjectId"
        type="warning"
        :closable="false"
        show-icon
        style="margin-bottom: 14px"
      >
        请先在顶部选择项目
      </el-alert>

      <div class="toolbar">
        <el-button type="primary" @click="fetchList" :icon="Refresh" :disabled="!currentProjectId">刷新</el-button>
        <el-radio-group v-model="viewMode" size="default" :disabled="!currentProjectId">
          <el-radio-button value="card">卡片</el-radio-button>
          <el-radio-button value="table">列表</el-radio-button>
        </el-radio-group>
        <el-button :disabled="!currentProjectId" @click="$router.push('/perf-sut-servers/overview')">多机总览</el-button>
        <el-button v-permission="'perf_scene:edit'" type="success" @click="openCreate" :disabled="!currentProjectId">
          新建
        </el-button>
      </div>

      <el-empty v-if="!loading && currentProjectId && !tableData.length" description="暂无被测服务器，请先新建" />

      <div v-if="viewMode === 'card'" class="cards" v-loading="loading">
        <div
          v-for="row in cardRows"
          :key="row.id"
          class="server-card"
          @click="goDetail(row)"
        >
          <div class="card-head">
            <strong>{{ row.name }}</strong>
            <div class="head-tags">
              <el-tag size="small" :type="row.status === 'online' ? 'success' : 'info'">
                {{ row.status === 'online' ? '在线' : '离线' }}
              </el-tag>
              <el-tag size="small" :type="row.sample_allowed ? 'success' : 'warning'">
                {{ row.sample_allowed ? '采样中' : '暂停采样' }}
              </el-tag>
            </div>
          </div>
          <div class="card-meta">{{ row.hostname || '-' }} · {{ row.role || '无角色' }}</div>
          <div class="card-stats">
            <div>
              <div class="label">当前CPU</div>
              <div class="val">{{ fmtMetric(row._latest?.cpu_pct) }}%</div>
            </div>
            <div>
              <div class="label">当前内存</div>
              <div class="val">{{ fmtMetric(row._latest?.mem_pct) }}%</div>
            </div>
            <div>
              <div class="label">磁盘占用</div>
              <div class="val">{{ fmtMetric(row._latest?.disk_pct) }}%</div>
            </div>
            <div>
              <div class="label">15分钟CPU峰值</div>
              <div class="val">{{ fmtMetric(row._summary15?.cpu_pct?.max) }}%</div>
            </div>
          </div>
          <div class="card-foot" @click.stop>
            <el-switch
              v-if="canEdit"
              :model-value="row.monitoring_enabled"
              inline-prompt
              active-text="监控开"
              inactive-text="监控关"
              @change="(v) => toggleMonitor(row, v)"
            />
            <el-tag v-else size="small" :type="row.monitoring_enabled ? 'success' : 'info'">
              监控{{ row.monitoring_enabled ? '开' : '关' }}
            </el-tag>
            <el-dropdown trigger="click" @command="(cmd) => onCardCommand(cmd, row)">
              <el-button link type="primary" size="small">更多</el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="detail">监控详情</el-dropdown-item>
                  <el-dropdown-item command="install">安装说明</el-dropdown-item>
                  <el-dropdown-item v-if="canEdit" command="edit">编辑</el-dropdown-item>
                  <el-dropdown-item v-if="canEdit" command="schedule">日程</el-dropdown-item>
                  <el-dropdown-item v-if="canEdit" command="agentSettings">采集参数</el-dropdown-item>
                  <el-dropdown-item v-if="canEdit" command="rotate" divided>轮换 Token</el-dropdown-item>
                  <el-dropdown-item v-if="canEdit" command="reset">重置采集器</el-dropdown-item>
                  <el-dropdown-item v-if="canEdit" command="delete" style="color: var(--el-color-danger)">删除</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </div>
      </div>

      <el-table v-else :data="tableData" v-loading="loading" stripe>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="name" label="名称" min-width="140" show-overflow-tooltip />
        <el-table-column prop="hostname" label="主机名" min-width="120" show-overflow-tooltip />
        <el-table-column prop="role" label="角色" width="100" show-overflow-tooltip />
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.status === 'online' ? 'success' : 'info'">
              {{ row.status === 'online' ? '在线' : '离线' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="监控" width="110" align="center">
          <template #default="{ row }">
            <el-switch
              v-if="canEdit"
              :model-value="row.monitoring_enabled"
              @change="(v) => toggleMonitor(row, v)"
            />
            <el-tag v-else size="small" :type="row.monitoring_enabled ? 'success' : 'info'">
              {{ row.monitoring_enabled ? '开' : '关' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="采样" width="90" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.sample_allowed ? 'success' : 'warning'">
              {{ row.sample_allowed ? '允许' : '暂停' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="last_heartbeat_at" label="最近心跳" width="170" show-overflow-tooltip />
        <el-table-column prop="last_metrics_at" label="最近指标" width="170" show-overflow-tooltip />
        <el-table-column label="操作" width="400" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="goDetail(row)">监控详情</el-button>
            <el-button link type="primary" size="small" @click="showInstall(row)">安装说明</el-button>
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
              type="primary"
              size="small"
              @click="openSchedule(row)"
            >日程</el-button>
            <el-button
              v-permission="'perf_scene:edit'"
              link
              type="primary"
              size="small"
              @click="openAgentSettings(row)"
            >采集参数</el-button>
            <el-button
              v-permission="'perf_scene:edit'"
              link
              type="warning"
              size="small"
              @click="rotateToken(row)"
            >轮换 Token</el-button>
            <el-button
              v-permission="'perf_scene:edit'"
              link
              type="info"
              size="small"
              @click="resetAgent(row)"
            >重置采集器</el-button>
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

      <el-dialog v-model="createVisible" title="新建被测服务器" width="480px" destroy-on-close>
        <el-form :model="form" label-width="88px">
          <el-form-item label="名称" required>
            <el-input v-model="form.name" maxlength="100" placeholder="如 demo-host / esp-01" />
          </el-form-item>
          <el-form-item label="角色">
            <el-input v-model="form.role" maxlength="64" placeholder="可选，如 app / db" />
          </el-form-item>
          <el-form-item label="启用监控">
            <el-switch v-model="form.monitoring_enabled" />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="createVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="saveCreate">创建</el-button>
        </template>
      </el-dialog>

      <el-dialog v-model="editVisible" title="编辑被测服务器" width="480px" destroy-on-close>
        <el-form :model="editForm" label-width="88px">
          <el-form-item label="名称" required>
            <el-input v-model="editForm.name" maxlength="100" />
          </el-form-item>
          <el-form-item label="角色">
            <el-input v-model="editForm.role" maxlength="64" />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="editVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="saveEdit">保存</el-button>
        </template>
      </el-dialog>

      <el-dialog v-model="scheduleVisible" title="监控日程" width="560px" destroy-on-close>
        <el-alert type="info" :closable="false" show-icon style="margin-bottom: 12px">
          days：周一=0 … 周日=6。关闭「启用监控」优先级高于日程。压测 force 采集（M3）可覆盖暂停窗。
        </el-alert>
        <el-form label-width="100px">
          <el-form-item label="模式">
            <el-radio-group v-model="scheduleForm.mode">
              <el-radio value="always">始终</el-radio>
              <el-radio value="windows">仅窗口内</el-radio>
              <el-radio value="pause_windows">窗口内暂停</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="时区">
            <el-input v-model="scheduleForm.timezone" placeholder="Asia/Shanghai" />
          </el-form-item>
          <template v-if="scheduleForm.mode !== 'always'">
            <div v-for="(w, idx) in scheduleWindows" :key="idx" class="sched-row">
              <el-time-picker
                v-model="w.start"
                format="HH:mm"
                value-format="HH:mm"
                placeholder="开始"
                style="width: 120px"
              />
              <span>~</span>
              <el-time-picker
                v-model="w.end"
                format="HH:mm"
                value-format="HH:mm"
                placeholder="结束"
                style="width: 120px"
              />
              <el-select v-model="w.days" multiple placeholder="起始星期" style="flex: 1">
                <el-option v-for="d in weekOptions" :key="d.v" :label="d.l" :value="d.v" />
              </el-select>
              <el-button link type="danger" @click="scheduleWindows.splice(idx, 1)">删</el-button>
            </div>
            <div class="sched-hint">跨午夜窗口：星期=起始日（如周一 22:00～02:00 含周二凌晨）</div>
            <el-button size="small" @click="scheduleWindows.push({ start: '09:00', end: '18:00', days: [0,1,2,3,4] })">
              添加时段
            </el-button>
          </template>
        </el-form>
        <template #footer>
          <el-button @click="scheduleVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="saveSchedule">保存</el-button>
        </template>
      </el-dialog>

      <el-dialog v-model="agentSettingsVisible" title="采集参数" width="480px" destroy-on-close>
        <el-alert type="info" :closable="false" show-icon style="margin-bottom: 12px">
          保存后经采集器心跳下发（约 30 秒内），热更新并回写被测机本地配置，无需 SSH 改文件或重启。
          「恢复本机默认」清除平台覆盖，采集器继续用本地 <code>agent_config.json</code>。
        </el-alert>
        <el-form label-width="120px">
          <el-form-item label="采样间隔(秒)">
            <el-input-number v-model="agentSettingsForm.interval_sec" :min="2" :max="60" :step="1" />
          </el-form-item>
          <el-form-item label="上报间隔(秒)">
            <el-input-number v-model="agentSettingsForm.upload_every_sec" :min="2" :max="3600" :step="1" />
            <div class="sched-hint">须 ≥ 采样间隔</div>
          </el-form-item>
          <el-form-item label="本机缓冲(小时)">
            <el-input-number v-model="agentSettingsForm.buffer_hours" :min="1" :max="168" :step="1" />
            <div class="sched-hint">断网补传窗口；默认 48（2 天）</div>
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button :loading="saving" @click="clearAgentSettings">恢复本机默认</el-button>
          <el-button @click="agentSettingsVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="saveAgentSettings">保存</el-button>
        </template>
      </el-dialog>

      <el-dialog
        v-model="tokenVisible"
        title="采集器 Token（仅显示一次）"
        width="640px"
        destroy-on-close
        :before-close="beforeCloseToken"
      >
        <el-alert type="warning" :closable="false" show-icon style="margin-bottom: 12px">
          请立即复制到 采集器的 <code>agent_config.json</code>。关闭后无法再查看明文，只能轮换。
        </el-alert>
        <el-input ref="tokenInputRef" v-model="plainToken" type="textarea" :rows="3" readonly />
        <div style="margin-top: 12px; display: flex; gap: 8px">
          <el-button type="primary" @click="copyToken">复制 Token</el-button>
          <el-button type="success" @click="confirmTokenSaved">我已保存</el-button>
        </div>
      </el-dialog>

      <el-dialog v-model="installVisible" title="被测监控采集器 · 安装说明" width="720px" destroy-on-close>
        <el-alert type="info" :closable="false" show-icon style="margin-bottom: 12px">
          {{ installHint || '明文 Token 仅在创建/轮换时可见；若已丢失请点「轮换 Token」。当前仅采主机 CPU/内存（及负载等附属字段），无磁盘/网卡。' }}
        </el-alert>
        <div class="install-hint">
          <p><strong>推荐用启动脚本</strong>（自动 venv、交互填平台/Token、可复用上次配置）：</p>
          <pre class="install-pre">cd /opt/sut_metrics_agent
chmod +x start.sh stop.sh
./start.sh          # 首次询问平台地址与 Token
tail -f agent.log   # 看是否 activated / uploaded
./stop.sh           # 停止

# 若报「bash\\r: No such file or directory」（Windows zip 换行）：
sed -i 's/\r$//' start.sh stop.sh && ./start.sh
# 或：.venv/bin/python agent_ctl.py start</pre>
          <p>下次再执行 <code>./start.sh</code> 可选：用上次配置 / 只更新 Token / 全部重填。</p>
          <p class="muted">也可手工：python3 -m venv .venv → pip install → 编辑 agent_config.json → python sut_metrics_agent.py。HTTP 平台须 allow_insecure_http=true。「重置采集器」用于换机/丢 data 后的 409，不换 Token。给 Linux 打包请用 <code>python tools/sut_metrics_agent/pack_zip.py</code>，勿用资源管理器直接压目录。</p>
        </div>
        <el-divider />
        <div v-if="installConfig" class="install-hint">
          <p>配置示例（token 需自行替换；HTTP 联调请把 allow_insecure_http 改为 true）：</p>
          <el-input
            type="textarea"
            :rows="12"
            readonly
            :model-value="JSON.stringify(installConfig, null, 2)"
          />
        </div>
        <template #footer>
          <el-button type="primary" @click="installVisible = false">关闭</el-button>
        </template>
      </el-dialog>
    </template>
  </PageCard>
</template>

<script setup>
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import PageCard from '@/components/PageCard.vue'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { UserStore } from '@/stores/module/UserStore'
import { perfSutServerApi } from '@/api/modules/perf'

const proStore = ProjectStore()
const uStore = UserStore()
const router = useRouter()
const loading = ref(false)
const saving = ref(false)
let listLoadSeq = 0
const tableData = ref([])
const overviewById = ref({})
const viewMode = ref('card')
const createVisible = ref(false)
const editVisible = ref(false)
const tokenVisible = ref(false)
const installVisible = ref(false)
const plainToken = ref('')
const tokenCopied = ref(false)
const tokenInputRef = ref(null)
const installHint = ref('')
const installConfig = ref(null)
const form = reactive({ name: '', role: '', monitoring_enabled: true })
const editForm = reactive({ id: null, name: '', role: '' })
const scheduleVisible = ref(false)
const scheduleServerId = ref(null)
const scheduleForm = reactive({ mode: 'always', timezone: 'Asia/Shanghai' })
const scheduleWindows = ref([])
const agentSettingsVisible = ref(false)
const agentSettingsServerId = ref(null)
const agentSettingsForm = reactive({
  interval_sec: 5,
  upload_every_sec: 15,
  buffer_hours: 48,
})
const weekOptions = [
  { v: 0, l: '一' },
  { v: 1, l: '二' },
  { v: 2, l: '三' },
  { v: 3, l: '四' },
  { v: 4, l: '五' },
  { v: 5, l: '六' },
  { v: 6, l: '日' },
]

const currentProjectId = computed(() => proStore.projectInfo?.id || null)
const canEdit = computed(() => uStore.hasPermission('perf_scene:edit'))

const cardRows = computed(() =>
  (tableData.value || []).map((row) => {
    const ov = overviewById.value[row.id] || {}
    return {
      ...row,
      _latest: ov.latest || null,
      _summary15: ov.summary_15m || null,
      sample_allowed: ov.sample_allowed != null ? ov.sample_allowed : row.sample_allowed,
      status: ov.status || row.status,
    }
  })
)

function fmtMetric(v) {
  if (v == null || Number.isNaN(Number(v))) return '-'
  return Math.round(Number(v) * 10) / 10
}

function errDetail(e) {
  return e?.response?.data?.detail || e?.data?.detail || e?.message || null
}

async function fetchList() {
  const pid = currentProjectId.value
  if (!pid) {
    tableData.value = []
    overviewById.value = {}
    return
  }
  const seq = ++listLoadSeq
  loading.value = true
  try {
    const [listRes, ovRes] = await Promise.all([
      perfSutServerApi.getList({ project_id: pid }),
      perfSutServerApi.getOverview({ project_id: pid }).catch(() => null),
    ])
    if (seq !== listLoadSeq) return
    const data = listRes?.data || listRes || {}
    tableData.value = data.data || []
    const ov = ovRes?.data || ovRes || {}
    const map = {}
    for (const item of ov.data || []) {
      if (item?.id != null) map[item.id] = item
    }
    overviewById.value = map
  } catch (e) {
    if (seq !== listLoadSeq) return
    ElMessage.error(errDetail(e) || '加载失败')
  } finally {
    if (seq === listLoadSeq) loading.value = false
  }
}

function onCardCommand(cmd, row) {
  if (cmd === 'detail') goDetail(row)
  else if (cmd === 'install') showInstall(row)
  else if (cmd === 'edit') openEdit(row)
  else if (cmd === 'schedule') openSchedule(row)
  else if (cmd === 'agentSettings') openAgentSettings(row)
  else if (cmd === 'rotate') rotateToken(row)
  else if (cmd === 'reset') resetAgent(row)
  else if (cmd === 'delete') handleDelete(row)
}

function openCreate() {
  form.name = ''
  form.role = ''
  form.monitoring_enabled = true
  createVisible.value = true
}

function openEdit(row) {
  editForm.id = row.id
  editForm.name = row.name || ''
  editForm.role = row.role || ''
  editVisible.value = true
}

async function saveCreate() {
  const pid = currentProjectId.value
  if (!pid) return
  if (!form.name.trim()) {
    ElMessage.warning('请填写名称')
    return
  }
  saving.value = true
  try {
    const res = await perfSutServerApi.create({
      project_id: pid,
      name: form.name.trim(),
      role: form.role.trim() || undefined,
      monitoring_enabled: form.monitoring_enabled,
    })
    const row = res?.data || res || {}
    createVisible.value = false
    plainToken.value = row.token || ''
    tokenCopied.value = false
    tokenVisible.value = true
    ElMessage.success('已创建')
    await fetchList()
  } catch (e) {
    ElMessage.error(errDetail(e) || '创建失败')
  } finally {
    saving.value = false
  }
}

async function saveEdit() {
  if (!editForm.id) return
  if (!editForm.name.trim()) {
    ElMessage.warning('请填写名称')
    return
  }
  saving.value = true
  try {
    await perfSutServerApi.update(editForm.id, {
      name: editForm.name.trim(),
      role: editForm.role.trim(),
    })
    editVisible.value = false
    ElMessage.success('已保存')
    await fetchList()
  } catch (e) {
    ElMessage.error(errDetail(e) || '保存失败')
  } finally {
    saving.value = false
  }
}

function openSchedule(row) {
  scheduleServerId.value = row.id
  const s = row.schedule || {}
  scheduleForm.mode = s.mode || 'always'
  scheduleForm.timezone = s.timezone || 'Asia/Shanghai'
  const key = scheduleForm.mode === 'pause_windows' ? 'pause_windows' : 'windows'
  const wins = s[key] || []
  scheduleWindows.value = wins.length
    ? wins.map((w) => ({
        start: w.start || '09:00',
        end: w.end || '18:00',
        days: Array.isArray(w.days) ? [...w.days] : [0, 1, 2, 3, 4],
      }))
    : [{ start: '09:00', end: '18:00', days: [0, 1, 2, 3, 4] }]
  scheduleVisible.value = true
}

async function saveSchedule() {
  if (!scheduleServerId.value) return
  let schedule
  if (scheduleForm.mode === 'always') {
    schedule = { mode: 'always', timezone: scheduleForm.timezone || 'Asia/Shanghai' }
  } else {
    const key = scheduleForm.mode === 'pause_windows' ? 'pause_windows' : 'windows'
    schedule = {
      mode: scheduleForm.mode,
      timezone: scheduleForm.timezone || 'Asia/Shanghai',
      [key]: scheduleWindows.value.map((w) => ({
        start: w.start || '00:00',
        end: w.end || '23:59',
        days: w.days || [],
      })),
    }
  }
  saving.value = true
  try {
    await perfSutServerApi.update(scheduleServerId.value, { schedule })
    scheduleVisible.value = false
    ElMessage.success('日程已保存')
    await fetchList()
  } catch (e) {
    ElMessage.error(errDetail(e) || '保存失败')
  } finally {
    saving.value = false
  }
}

function openAgentSettings(row) {
  agentSettingsServerId.value = row.id
  const s = row.agent_settings || {}
  agentSettingsForm.interval_sec = Number(s.interval_sec) || 5
  agentSettingsForm.upload_every_sec = Number(s.upload_every_sec) || 15
  agentSettingsForm.buffer_hours = Number(s.buffer_hours) || 48
  agentSettingsVisible.value = true
}

async function saveAgentSettings() {
  if (!agentSettingsServerId.value) return
  if (agentSettingsForm.upload_every_sec < agentSettingsForm.interval_sec) {
    ElMessage.warning('上报间隔不能小于采样间隔')
    return
  }
  saving.value = true
  try {
    await perfSutServerApi.update(agentSettingsServerId.value, {
      agent_settings: {
        interval_sec: agentSettingsForm.interval_sec,
        upload_every_sec: agentSettingsForm.upload_every_sec,
        buffer_hours: agentSettingsForm.buffer_hours,
      },
    })
    agentSettingsVisible.value = false
    ElMessage.success('已保存，采集器约 30 秒内生效')
    await fetchList()
  } catch (e) {
    ElMessage.error(errDetail(e) || '保存失败')
  } finally {
    saving.value = false
  }
}

async function clearAgentSettings() {
  if (!agentSettingsServerId.value) return
  saving.value = true
  try {
    await perfSutServerApi.update(agentSettingsServerId.value, { agent_settings: null })
    agentSettingsVisible.value = false
    ElMessage.success('已清除平台覆盖，采集器沿用本机配置')
    await fetchList()
  } catch (e) {
    ElMessage.error(errDetail(e) || '清除失败')
  } finally {
    saving.value = false
  }
}

async function toggleMonitor(row, enabled) {
  try {
    await perfSutServerApi.update(row.id, { monitoring_enabled: !!enabled })
    ElMessage.success(enabled ? '已启用监控' : '已关闭监控（采集器仍可心跳）')
    await fetchList()
  } catch (e) {
    ElMessage.error(errDetail(e) || '更新失败')
    await fetchList()
  }
}

function goDetail(row) {
  router.push({ path: `/perf-sut-servers/${row.id}` })
}

async function showInstall(row) {
  installHint.value = ''
  const origin = window.location.origin || ''
  installConfig.value = {
    platform: origin,
    token: '<粘贴一次性 Token>',
    allow_insecure_http: String(origin).startsWith('http://'),
    interval_sec: 5,
    upload_every_sec: 15,
    buffer_hours: 48,
    data_dir: './data',
  }
  installVisible.value = true
  try {
    const res = await perfSutServerApi.getInstallSnippet(row.id)
    const data = res?.data || res || {}
    installHint.value = data.hint || ''
    const cfg = data.config_example || {}
    const platform = origin || cfg.platform || ''
    installConfig.value = {
      ...cfg,
      platform,
      allow_insecure_http:
        cfg.allow_insecure_http ?? String(platform).startsWith('http://'),
    }
  } catch (e) {
    installHint.value = `服务器 #${row.id}「${row.name}」：明文 Token 仅创建/轮换时可见，丢失请轮换。推荐 venv 安装，详见 采集器 README。`
    ElMessage.error(errDetail(e) || '加载安装说明失败')
  }
}

async function rotateToken(row) {
  try {
    await ElMessageBox.confirm('轮换后旧 Token 立即失效，需更新采集器配置。继续？', '轮换 Token', {
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    const res = await perfSutServerApi.rotateToken(row.id)
    const data = res?.data || res || {}
    plainToken.value = data.token || ''
    tokenCopied.value = false
    tokenVisible.value = true
    ElMessage.success('已轮换')
  } catch (e) {
    ElMessage.error(errDetail(e) || '轮换失败')
  }
}

async function resetAgent(row) {
  try {
    await ElMessageBox.confirm(
      `清空「${row.name}」的采集器身份绑定？\n适用于：换机、删了 data 目录导致 agent_uid 变化后上报 409。\n不会删除历史曲线，也不会更换 Token。重置后重新启动采集器即可重新激活。`,
      '重置采集器绑定',
      { type: 'warning' }
    )
  } catch {
    return
  }
  try {
    await perfSutServerApi.resetAgent(row.id)
    ElMessage.success('已重置采集器绑定')
    await fetchList()
  } catch (e) {
    ElMessage.error(errDetail(e) || '重置失败')
  }
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(
      `删除被测服务器「${row.name}」？采集器 Token 将失效，历史曲线不再在列表中展示。`,
      '确认删除',
      { type: 'warning' }
    )
  } catch {
    return
  }
  try {
    await perfSutServerApi.delete(row.id)
    ElMessage.success('已删除')
    await fetchList()
  } catch (e) {
    ElMessage.error(errDetail(e) || '删除失败')
  }
}

async function copyToken() {
  if (!plainToken.value) {
    ElMessage.warning('无 Token 可复制，请轮换后重试')
    return
  }
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(plainToken.value)
    } else {
      throw new Error('no clipboard')
    }
    tokenCopied.value = true
    ElMessage.success('已复制')
  } catch {
    try {
      await nextTick()
      const el = tokenInputRef.value?.textarea || tokenInputRef.value?.$el?.querySelector?.('textarea')
      if (el) {
        el.focus()
        el.select()
        document.execCommand('copy')
        tokenCopied.value = true
        ElMessage.success('已复制')
        return
      }
    } catch {
      /* fallthrough */
    }
    ElMessage.error('自动复制失败，请手动选中文本复制')
  }
}

function confirmTokenSaved() {
  tokenCopied.value = true
  tokenVisible.value = false
}

async function beforeCloseToken(done) {
  if (tokenCopied.value || !plainToken.value) {
    done()
    return
  }
  try {
    await ElMessageBox.confirm(
      '尚未确认已保存 Token。关闭后无法再查看明文，只能轮换。确定关闭？',
      '未保存 Token',
      { type: 'warning', confirmButtonText: '仍要关闭', cancelButtonText: '返回复制' }
    )
    done()
  } catch {
    /* stay open */
  }
}

watch(
  () => proStore.projectInfo?.id,
  (id) => {
    if (id) fetchList()
    else {
      tableData.value = []
      overviewById.value = {}
    }
  },
  { immediate: true }
)
</script>

<style scoped>
.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
  align-items: center;
}
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 14px;
}
.server-card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  padding: 14px;
  cursor: pointer;
  background: var(--el-fill-color-blank);
  transition: border-color 0.15s ease;
}
.server-card:hover {
  border-color: var(--el-color-primary-light-5);
}
.card-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 6px;
}
.head-tags {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}
.card-meta {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 12px;
}
.card-stats {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-bottom: 12px;
}
.card-stats .label {
  font-size: 11px;
  color: var(--el-text-color-secondary);
}
.card-stats .val {
  font-size: 16px;
  font-weight: 600;
}
.card-foot {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-top: 1px solid var(--el-border-color-extra-light);
  padding-top: 10px;
}
.install-hint {
  font-size: 13px;
  line-height: 1.7;
  color: var(--el-text-color-regular);
}
.install-hint code {
  font-size: 12px;
}
.install-pre {
  margin: 8px 0 12px;
  padding: 10px 12px;
  background: var(--el-fill-color-light);
  border-radius: 6px;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  overflow-x: auto;
}
.install-hint .muted {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.sched-row {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}
.sched-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}
</style>
