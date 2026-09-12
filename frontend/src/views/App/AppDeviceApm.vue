<template>
  <PageCard class="app-device-apm-page">
    <template #title><span>设备性能监控</span></template>
    <template #main>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        style="margin-bottom: 12px"
        title="在真机上实时采集指定包名的资源指标。可在下方勾选采集项（默认 CPU/内存/FPS/Jank/电量）。CPU 为单核 100% 口径（多核可>100）。会占用设备锁；停止后自动落库，也可手动「保存记录」。"
      />

      <el-alert
        v-if="sessionError"
        type="error"
        :closable="false"
        show-icon
        style="margin-bottom: 12px"
        :title="sessionError"
      />
      <el-alert
        v-if="persistError"
        type="warning"
        :closable="false"
        show-icon
        style="margin-bottom: 12px"
        :title="`终态已接收但落库失败：${persistError}。可点击「保存记录」重试。`"
      />
      <el-alert
        v-if="partialData"
        type="warning"
        :closable="false"
        show-icon
        style="margin-bottom: 12px"
        title="本次数据为部分可用（partial_data），曲线/峰值可能不完整。"
      />

      <el-form inline class="toolbar">
        <el-form-item label="执行设备" required>
          <el-select
            v-model="deviceId"
            placeholder="在线 App Runner"
            filterable
            style="width: 260px"
            :disabled="running || !canExecute"
          >
            <el-option
              v-for="d in appDevices"
              :key="d.id"
              :label="`${d.name || d.username} (${d.app_udid || d.id})`"
              :value="d.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="UDID">
          <el-input v-model="appUdid" placeholder="留空用设备登记值" style="width: 200px" :disabled="running || !canExecute" />
        </el-form-item>
        <el-form-item label="包名" required>
          <el-input
            v-model="pkgName"
            placeholder="如 com.example.app"
            style="width: 240px"
            :disabled="running || !canExecute"
          />
        </el-form-item>
        <el-form-item label="间隔(ms)">
          <el-input-number v-model="intervalMs" :min="200" :max="10000" :step="100" :disabled="running || !canExecute" />
        </el-form-item>
        <el-form-item>
          <el-button v-if="!running && canExecute" type="primary" :loading="starting" @click="startMonitor">开始监控</el-button>
          <el-button v-else-if="running && canExecute" type="danger" :loading="stopping" @click="stopMonitor">停止</el-button>
          <el-button
            v-if="canExecute && sessionId && (status === 'finished' || status === 'failed')"
            :loading="saving"
            @click="saveRecord"
          >
            保存记录
          </el-button>
          <el-tag v-if="sessionId" style="margin-left: 8px" :type="statusTagType">{{ statusLabel }}</el-tag>
        </el-form-item>
      </el-form>

      <el-form-item label="采集指标" class="metrics-row">
        <el-checkbox-group v-model="selectedMetrics" :disabled="running || !canExecute" size="small">
          <el-checkbox v-for="m in METRIC_OPTIONS" :key="m.key" :label="m.key">{{ m.label }}</el-checkbox>
        </el-checkbox-group>
        <el-text type="info" size="small" style="margin-left: 8px">
          默认轻量；网络/GPU/磁盘/热状态需勾选后才会采集
        </el-text>
      </el-form-item>

      <AppDeviceApmPanel
        :summary="displaySummary"
        :series="liveSeries"
        :thresholds="thresholds"
        :live="running"
        :collected-metrics="panelCollectedMetrics"
        :show-empty="!running && !liveSeries.length && !summary"
      />

      <el-divider content-position="left">监控记录</el-divider>
      <div class="history-toolbar">
        <el-button size="small" @click="loadHistory">刷新列表</el-button>
        <el-text type="info" size="small">独立监控结束后自动写入本列表；也可点「保存记录」补写。</el-text>
      </div>
      <el-table :data="historyRows" size="small" border v-loading="historyLoading" style="margin-bottom: 8px">
        <el-table-column prop="session_id" label="会话 ID" min-width="160" show-overflow-tooltip />
        <el-table-column prop="pkg_name" label="包名" min-width="140" show-overflow-tooltip />
        <el-table-column prop="app_udid" label="UDID" min-width="120" show-overflow-tooltip />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">{{ historyStatusLabel(row.status) }}</template>
        </el-table-column>
        <el-table-column label="采样点" width="80">
          <template #default="{ row }">{{ row.sample_count ?? '—' }}</template>
        </el-table-column>
        <el-table-column label="CPU峰值" width="100">
          <template #default="{ row }">{{ formatCpuPeak(row.cpu_pct_max) }}</template>
        </el-table-column>
        <el-table-column prop="username" label="操作人" width="100" show-overflow-tooltip />
        <el-table-column label="时间" min-width="160">
          <template #default="{ row }">{{ formatHistoryTime(row.create_time) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="viewHistory(row)">查看</el-button>
            <el-button v-if="canExecute" link type="danger" @click="deleteHistory(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination
        v-model:current-page="historyPage"
        v-model:page-size="historyPageSize"
        :page-sizes="[10, 20, 50]"
        :total="historyTotal"
        layout="total, sizes, prev, pager, next"
        small
        style="margin-bottom: 16px; justify-content: flex-end"
        @current-change="loadHistory"
        @size-change="onHistorySizeChange"
      />

      <el-divider content-position="left">双记录对比</el-divider>
      <el-form inline class="toolbar">
        <el-form-item label="左侧">
          <el-select v-model="cmpLeftType" style="width: 110px">
            <el-option label="用例记录" value="case" />
            <el-option label="套件记录" value="suite" />
            <el-option label="计划记录" value="plan" />
            <el-option label="独立会话" value="session" />
          </el-select>
          <el-input v-model="cmpLeftId" placeholder="ID" style="width: 140px; margin-left: 6px" />
        </el-form-item>
        <el-form-item label="右侧">
          <el-select v-model="cmpRightType" style="width: 110px">
            <el-option label="用例记录" value="case" />
            <el-option label="套件记录" value="suite" />
            <el-option label="计划记录" value="plan" />
            <el-option label="独立会话" value="session" />
          </el-select>
          <el-input v-model="cmpRightId" placeholder="ID" style="width: 140px; margin-left: 6px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" plain :loading="comparing" @click="runCompare">对比</el-button>
        </el-form-item>
      </el-form>
      <el-table v-if="cmpRows.length" :data="cmpRows" size="small" border style="margin-bottom: 16px">
        <el-table-column prop="metric" label="指标" width="200" />
        <el-table-column prop="left" label="左侧" />
        <el-table-column prop="right" label="右侧" />
        <el-table-column prop="delta" label="差值(右-左)" />
        <el-table-column prop="unit" label="单位" width="70" />
        <el-table-column prop="better_direction" label="方向" width="90" />
      </el-table>
      <el-alert
        type="warning"
        :closable="false"
        show-icon
        title="iOS 设备性能采集尚未开放。当前仅 Android；GPU 在非高通机型上可能显示不可用。"
        style="margin-top: 8px"
      />
    </template>
  </PageCard>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import PageCard from '@/components/PageCard.vue'
import { appDeviceApmApi, deviceApi } from '@/api'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { UserStore } from '@/stores/module/UserStore'
import AppDeviceApmPanel from './components/AppDeviceApmPanel.vue'
import dateTools from '@/tools/dateTools'

const STORAGE_KEY = 'app_device_apm_active_session'
const METRIC_OPTIONS = [
  { key: 'cpu', label: 'CPU' },
  { key: 'memory', label: '内存' },
  { key: 'fps', label: 'FPS' },
  { key: 'jank', label: 'Jank' },
  { key: 'battery', label: '电量' },
  { key: 'network', label: '网络' },
  { key: 'gpu', label: 'GPU' },
  { key: 'disk', label: '磁盘' },
  { key: 'thermal', label: '热状态' },
]

const proStore = ProjectStore()
const uStore = UserStore()
const canExecute = computed(() => uStore.hasPermission('app_case:execute'))
const devices = ref([])
const deviceId = ref('')
const appUdid = ref('')
const pkgName = ref('')
const intervalMs = ref(1000)
const selectedMetrics = ref(['cpu', 'memory', 'fps', 'jank', 'battery'])
const sessionId = ref('')
const status = ref('')
const starting = ref(false)
const stopping = ref(false)
const saving = ref(false)
const liveSeries = ref([])
const summary = ref(null)
const thresholds = ref(null)
const sessionError = ref('')
const persistError = ref('')
const partialData = ref(false)
const activeMetrics = ref([])
const comparing = ref(false)
const cmpLeftType = ref('case')
const cmpRightType = ref('case')
const cmpLeftId = ref('')
const cmpRightId = ref('')
const cmpRows = ref([])
const historyRows = ref([])
const historyLoading = ref(false)
const historyPage = ref(1)
const historyPageSize = ref(20)
const historyTotal = ref(0)
const historyDeleteMode = ref('logical')
let pollTimer = null
let waitFinalTimer = null
let lastTs = 0

const HISTORY_STATUS_MAP = {
  starting: '启动中',
  running: '采集中',
  stopping: '停止中',
  finished: '已结束',
  failed: '失败',
}

function historyStatusLabel(status) {
  return HISTORY_STATUS_MAP[status] || status || '—'
}

function formatCpuPeak(v) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return '—'
  return `${Number(v).toFixed(1)}%`
}

function formatHistoryTime(t) {
  if (!t) return '—'
  try {
    return dateTools.rTime(t)
  } catch (_) {
    return String(t).replace('T', ' ').slice(0, 19)
  }
}

function getDeleteConfirmMessage() {
  if (historyDeleteMode.value === 'physical') {
    return '将立即从数据库永久删除该监控记录，此操作不可恢复，确定继续吗？'
  }
  if (historyDeleteMode.value === 'recycle_bin') {
    return '记录将从列表中隐藏（可按平台回收策略处理），确定继续吗？'
  }
  return '记录将从列表中隐藏（逻辑删除），确定继续吗？'
}

const appDevices = computed(() =>
  (devices.value || []).filter((d) => {
    const types = d.runner_engine_types || ['web']
    return types.includes('app')
  })
)

const running = computed(() => ['starting', 'running', 'stopping'].includes(status.value))
/** 采集中用会话实际指标；空闲时用上方勾选，便于说明/预览与趋势图对齐 */
const panelCollectedMetrics = computed(() =>
  activeMetrics.value?.length ? activeMetrics.value : selectedMetrics.value
)
const statusLabel = computed(() => {
  const map = {
    starting: '启动中',
    running: '采集中',
    stopping: '停止中',
    finished: '已结束',
    failed: '失败',
  }
  return map[status.value] || status.value || '空闲'
})
const statusTagType = computed(() => {
  if (status.value === 'running') return 'success'
  if (status.value === 'failed') return 'danger'
  if (status.value === 'stopping' || status.value === 'starting') return 'warning'
  return 'info'
})

function maxOf(arr) {
  const vals = arr.filter((v) => v != null && !Number.isNaN(Number(v))).map(Number)
  return vals.length ? Math.max(...vals) : null
}
function minOf(arr) {
  const vals = arr.filter((v) => v != null && !Number.isNaN(Number(v))).map(Number)
  return vals.length ? Math.min(...vals) : null
}

const THERMAL_RANK = {
  none: 0,
  light: 1,
  moderate: 2,
  severe: 3,
  critical: 4,
  emergency: 5,
  shutdown: 6,
}

function worstThermal(pts) {
  let best = null
  let bestRank = -1
  for (const p of pts || []) {
    const name = String(p?.thermal_status || '').trim().toLowerCase()
    if (!name) continue
    const rank = THERMAL_RANK[name] ?? -1
    if (rank > bestRank) {
      bestRank = rank
      best = name
    }
  }
  return best
}

function fpsOkAvg(pts) {
  const vals = (pts || [])
    .filter(
      (p) =>
        p?.fps != null &&
        Number(p.fps) > 0 &&
        (p?.quality?.fps == null || p.quality.fps === 'ok')
    )
    .map((p) => Number(p.fps))
    .filter((v) => !Number.isNaN(v))
  if (!vals.length) return null
  return Math.round((vals.reduce((a, b) => a + b, 0) / vals.length) * 100) / 100
}

const displaySummary = computed(() => {
  if (summary.value && Object.keys(summary.value).length) return summary.value
  if (!liveSeries.value.length) return null
  const pts = liveSeries.value
  const last = pts[pts.length - 1] || {}
  return {
    sample_count: pts.length,
    cpu_pct_max: maxOf(pts.map((p) => p.cpu_pct)),
    mem_pss_mb_max: maxOf(pts.map((p) => p.mem_pss_mb)),
    mem_java_heap_mb_max: maxOf(pts.map((p) => p.mem_java_heap_mb)),
    mem_native_heap_mb_max: maxOf(pts.map((p) => p.mem_native_heap_mb)),
    mem_graphics_mb_max: maxOf(pts.map((p) => p.mem_graphics_mb)),
    fps_avg: fpsOkAvg(pts),
    janky_pct_max: maxOf(pts.map((p) => p.janky_pct)),
    gpu_busy_pct_max: maxOf(pts.map((p) => p.gpu_busy_pct)),
    disk_free_mb_min: minOf(pts.map((p) => p.disk_free_mb)),
    thermal_status_worst: worstThermal(pts),
    battery_pct_last: last.battery_pct,
    temp_c_max: maxOf(pts.map((p) => p.temp_c)),
    net_rx_kb_delta: last.net_rx_kb,
    net_tx_kb_delta: last.net_tx_kb,
    first_ts_ms: pts[0]?.ts_ms,
    last_ts_ms: last.ts_ms,
    thresholds: thresholds.value,
    live_window_approx: true,
    quality_notes: {
      live_basis: '最近轮询窗口近似；网络为会话累计；热状态取最差；FPS 为有效帧率平均',
    },
  }
})

function persistLocalSession() {
  try {
    if (!sessionId.value) {
      localStorage.removeItem(STORAGE_KEY)
      return
    }
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        session_id: sessionId.value,
        project_id: proStore.projectInfo?.id,
        device_id: deviceId.value,
        pkg_name: pkgName.value,
        metrics: activeMetrics.value,
      })
    )
  } catch (_) {
    /* ignore */
  }
}

function readLocalSession() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    return JSON.parse(raw)
  } catch (_) {
    return null
  }
}

async function loadDevices() {
  try {
    const res = await deviceApi.getList({ page: 1, size: 200, status: '在线' })
    devices.value = res?.data?.data || res?.data?.items || res?.data?.list || res?.data || []
    if (!Array.isArray(devices.value)) devices.value = []
  } catch (e) {
    devices.value = []
  }
}

function clearPoll() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
  if (waitFinalTimer) {
    clearInterval(waitFinalTimer)
    waitFinalTimer = null
  }
}

function mergePoints(points) {
  if (!Array.isArray(points) || !points.length) return
  const map = new Map(liveSeries.value.map((p) => [p.ts_ms, p]))
  for (const p of points) {
    if (!p || p.ts_ms == null) continue
    map.set(p.ts_ms, p)
    if (Number(p.ts_ms) > lastTs) lastTs = Number(p.ts_ms)
  }
  liveSeries.value = Array.from(map.values()).sort((a, b) => Number(a.ts_ms) - Number(b.ts_ms)).slice(-1800)
}

function applySessionPayload(data, { resumePoll = false } = {}) {
  if (!data) return
  sessionId.value = data.session_id || sessionId.value
  status.value = data.status || status.value
  if (data.thresholds) thresholds.value = data.thresholds
  if (data.interval_ms != null && Number(data.interval_ms) > 0) {
    intervalMs.value = Number(data.interval_ms)
  }
  if (Array.isArray(data.metrics) && data.metrics.length) {
    activeMetrics.value = data.metrics
    selectedMetrics.value = [...data.metrics]
  }
  if (data.pkg_name) pkgName.value = data.pkg_name
  if (data.device_id) deviceId.value = data.device_id
  sessionError.value = data.error || data.summary?.error || ''
  persistError.value = data.persist_error || ''
  partialData.value = Boolean(data.summary?.partial_data || data.partial_data)
  mergePoints(data.points || [])
  if (data.summary) summary.value = data.summary
  if (Array.isArray(data.series) && data.series.length) {
    liveSeries.value = data.series
    lastTs = Number(data.series[data.series.length - 1]?.ts_ms || lastTs)
  }
  persistLocalSession()
  if (resumePoll && running.value) {
    clearPoll()
    pollTimer = setInterval(pollOnce, 2000)
  }
}

async function pollOnce() {
  if (!sessionId.value) return
  try {
    const res = await appDeviceApmApi.getSession(sessionId.value, { after_ts_ms: lastTs || undefined })
    const data = res?.data?.data || res?.data || {}
    applySessionPayload(data)
    if (['finished', 'failed', 'gone'].includes(data.status)) {
      clearPoll()
      if (data.status === 'finished' || data.status === 'failed') {
        // 终态后刷新历史
        loadHistory()
      }
    }
  } catch (e) {
    const code = e?.response?.status
    if (code === 403) {
      clearPoll()
      status.value = 'failed'
      ElMessage.error('无权限查看该监控会话（需要 app_case:view）')
      return
    }
    if (code === 404) {
      clearPoll()
      status.value = 'gone'
      localStorage.removeItem(STORAGE_KEY)
      ElMessage.warning('监控会话已过期或不存在')
    }
  }
}

async function startMonitor() {
  if (!deviceId.value) {
    ElMessage.warning('请选择执行设备')
    return
  }
  if (!pkgName.value.trim()) {
    ElMessage.warning('请填写应用包名')
    return
  }
  if (!selectedMetrics.value.length) {
    ElMessage.warning('请至少勾选一项采集指标')
    return
  }
  const projectId = proStore.projectInfo?.id
  if (!projectId) {
    ElMessage.warning('请先选择项目')
    return
  }
  starting.value = true
  try {
    const res = await appDeviceApmApi.startSession({
      project_id: projectId,
      device_id: deviceId.value,
      app_udid: appUdid.value || '',
      pkg_name: pkgName.value.trim(),
      interval_ms: intervalMs.value,
      metrics: selectedMetrics.value,
    })
    const data = res?.data?.data || res?.data || {}
    liveSeries.value = []
    summary.value = null
    lastTs = 0
    activeMetrics.value = data.metrics || selectedMetrics.value
    applySessionPayload(data, { resumePoll: true })
    await pollOnce()
    ElMessage.success(data.resumed ? '已恢复进行中的监控' : '已开始监控')
  } catch (e) {
    const msg = e?.response?.data?.detail || e?.message || '启动失败'
    ElMessage.error(typeof msg === 'string' ? msg : '启动失败')
  } finally {
    starting.value = false
  }
}

async function stopMonitor() {
  if (!sessionId.value) return
  stopping.value = true
  try {
    await appDeviceApmApi.stopSession(sessionId.value)
    status.value = 'stopping'
    persistLocalSession()
    await pollOnce()
    let n = 0
    clearPoll()
    waitFinalTimer = setInterval(async () => {
      n += 1
      await pollOnce()
      // Backend STOPPING_STALE≈90s + stale 扫描≈60s，最坏约 150s；覆盖到 160s
      if (!running.value) {
        clearPoll()
        return
      }
      if (n > 160) {
        clearPoll()
        ElMessage.warning('停止仍在后台清理中，可稍后刷新查看终态结果')
      }
    }, 1000)
    ElMessage.success('已请求停止')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '停止失败')
  } finally {
    stopping.value = false
  }
}

async function saveRecord() {
  if (!sessionId.value) {
    ElMessage.warning('没有可保存的会话')
    return
  }
  saving.value = true
  try {
    await appDeviceApmApi.persistSession(sessionId.value)
    ElMessage.success('已保存到监控记录')
    await loadHistory()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

async function loadHistory() {
  const projectId = proStore.projectInfo?.id
  if (!projectId) return
  historyLoading.value = true
  try {
    const res = await appDeviceApmApi.listSessions({
      project_id: projectId,
      page: historyPage.value,
      size: historyPageSize.value,
    })
    const data = res?.data?.data || res?.data || {}
    historyRows.value = data.items || []
    historyTotal.value = Number(data.total || 0)
    if (data.delete_mode) historyDeleteMode.value = data.delete_mode
  } catch (e) {
    historyRows.value = []
    historyTotal.value = 0
  } finally {
    historyLoading.value = false
  }
}

function onHistorySizeChange() {
  historyPage.value = 1
  loadHistory()
}

async function deleteHistory(row) {
  if (!row?.session_id) return
  try {
    await ElMessageBox.confirm(getDeleteConfirmMessage(), '删除监控记录', {
      type: 'warning',
      confirmButtonText: '确定',
      cancelButtonText: '取消',
    })
    await appDeviceApmApi.deleteHistory(row.session_id)
    ElMessage.success('已删除')
    if (sessionId.value === row.session_id && !running.value) {
      resetLiveUi()
    }
    // 删空当前页时回退一页
    if (historyRows.value.length <= 1 && historyPage.value > 1) {
      historyPage.value -= 1
    }
    await loadHistory()
  } catch (e) {
    if (e === 'cancel' || e === 'close') return
    ElMessage.error(e?.response?.data?.detail || '删除失败')
  }
}

async function viewHistory(row) {
  if (!row?.session_id) return
  if (running.value && sessionId.value && sessionId.value !== row.session_id) {
    ElMessage.warning('当前仍有监控在采集中，请先停止后再查看历史记录')
    return
  }
  try {
    const res = await appDeviceApmApi.getSession(row.session_id)
    const data = res?.data?.data || res?.data || {}
    clearPoll()
    lastTs = 0
    liveSeries.value = []
    summary.value = null
    applySessionPayload(data)
    if (running.value) {
      pollTimer = setInterval(pollOnce, 2000)
    } else {
      localStorage.removeItem(STORAGE_KEY)
    }
    ElMessage.success('已加载该监控记录')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '加载失败')
  }
}

function resetLiveUi() {
  clearPoll()
  sessionId.value = ''
  status.value = ''
  liveSeries.value = []
  summary.value = null
  thresholds.value = null
  sessionError.value = ''
  persistError.value = ''
  partialData.value = false
  lastTs = 0
  localStorage.removeItem(STORAGE_KEY)
}

async function restoreLocalSession() {
  const saved = readLocalSession()
  if (!saved?.session_id) return
  const projectId = proStore.projectInfo?.id
  if (!projectId) return
  if (saved.project_id && Number(saved.project_id) !== Number(projectId)) return
  try {
    const res = await appDeviceApmApi.getSession(saved.session_id)
    const data = res?.data?.data || res?.data || {}
    applySessionPayload(data, { resumePoll: true })
    if (['finished', 'failed'].includes(data.status)) {
      localStorage.removeItem(STORAGE_KEY)
    }
  } catch (_) {
    localStorage.removeItem(STORAGE_KEY)
  }
}

async function runCompare() {
  if (!cmpLeftId.value || !cmpRightId.value) {
    ElMessage.warning('请填写左右两侧记录 ID')
    return
  }
  comparing.value = true
  try {
    const res = await appDeviceApmApi.compare({
      left_type: cmpLeftType.value,
      left_id: String(cmpLeftId.value).trim(),
      right_type: cmpRightType.value,
      right_id: String(cmpRightId.value).trim(),
    })
    const data = res?.data?.data || res?.data || {}
    cmpRows.value = data.rows || []
    if (!cmpRows.value.length) ElMessage.info('无可对比指标（两侧可能都未采集）')
  } catch (e) {
    cmpRows.value = []
    ElMessage.error(e?.response?.data?.detail || '对比失败')
  } finally {
    comparing.value = false
  }
}

watch(
  () => proStore.projectInfo?.id,
  async (pid, prev) => {
    if (prev && pid && Number(pid) !== Number(prev)) {
      resetLiveUi()
      historyPage.value = 1
    }
    if (pid) {
      await restoreLocalSession()
      await loadHistory()
    }
  }
)

onMounted(async () => {
  await loadDevices()
  if (proStore.projectInfo?.id) {
    await restoreLocalSession()
    await loadHistory()
  }
})

onBeforeUnmount(() => {
  clearPoll()
  persistLocalSession()
})
</script>

<style scoped lang="scss">
.toolbar {
  margin-bottom: 8px;
}
.metrics-row {
  margin-bottom: 8px;
  width: 100%;
}
.history-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}
</style>
