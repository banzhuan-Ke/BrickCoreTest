<template>
  <div class="cron-run-config">
    <el-alert type="info" :closable="false" show-icon class="cron-run-config__hint">
      <template #title>执行器配置（给定时用，与计划页「运行」弹窗无关）</template>
      <div>
        可勾选 Web 执行器并配置权重/并发，保存后到点按此派发。留空则沿用旧策略：全部在线 Web 机等权（并行）或第一台（串行）。
        列表含离线机；已勾选但离线的会保留，到点用在线子集。App-only 执行器不会出现在此列表。
      </div>
    </el-alert>
    <el-form-item label="浏览器：">
      <el-select v-model="local.browser_type" style="width: 160px">
        <el-option label="Chromium" value="chromium" />
        <el-option label="Firefox" value="firefox" />
        <el-option label="WebKit" value="webkit" />
      </el-select>
      <el-checkbox v-model="local.headless" style="margin-left: 16px">无头模式</el-checkbox>
    </el-form-item>
    <el-form-item v-if="!taskParallel" label="首选执行器：">
      <el-select
        v-model="local.device_id"
        clearable
        filterable
        placeholder="可选；不选则用列表第一台在线机"
        style="width: 280px"
      >
        <el-option
          v-for="row in deviceRows"
          :key="row.id"
          :label="`${row.name || row.username} (${row.ip})`"
          :value="row.id"
        />
      </el-select>
      <el-input-number
        v-model="local.concurrency"
        :min="1"
        :max="20"
        size="small"
        controls-position="right"
        style="margin-left: 12px; width: 120px"
      />
      <span class="cron-run-config__tip">串行并发</span>
    </el-form-item>
    <el-form-item :label="taskParallel ? '执行器：' : '勾选（可选）：'">
      <el-table :data="deviceRows" size="small" border table-layout="fixed" class="cron-run-config__table">
        <el-table-column label="选用" width="52" align="center">
          <template #default="{ row }">
            <el-checkbox v-model="row.selected" />
          </template>
        </el-table-column>
        <el-table-column label="执行器" min-width="160">
          <template #default="{ row }">
            <div>{{ row.name || row.username }}</div>
            <div class="cron-run-config__ip">{{ row.ip }}</div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="72" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.status === '在线'" type="success" size="small">在线</el-tag>
            <el-tag v-else type="info" size="small">离线</el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="taskParallel" label="权重" width="110" align="center">
          <template #default="{ row }">
            <el-input-number
              v-model="row.weight"
              :min="1"
              :max="100"
              size="small"
              :disabled="!row.selected"
              controls-position="right"
            />
          </template>
        </el-table-column>
        <el-table-column label="并发" width="110" align="center">
          <template #default="{ row }">
            <el-input-number
              v-model="row.concurrency"
              :min="1"
              :max="20"
              size="small"
              :disabled="!row.selected"
              controls-position="right"
            />
          </template>
        </el-table-column>
      </el-table>
      <el-button link type="primary" style="margin-top: 6px" @click="reloadDevices()">刷新在线设备</el-button>
    </el-form-item>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import http from '@/api/index'
import { deviceSupportsEngine } from '@/utils/runnerDevice'

defineProps({
  taskParallel: { type: Boolean, default: false },
})

const deviceRows = ref([])
const local = reactive({
  browser_type: 'chromium',
  headless: true,
  device_id: '',
  concurrency: 1,
})

function emptyLocal() {
  local.browser_type = 'chromium'
  local.headless = true
  local.device_id = ''
  local.concurrency = 1
}

async function reloadDevices(cfgDevices = null) {
  // 拉全量 Web 能力机（含离线），避免编辑保存时把已勾选但当前离线的执行器清掉
  const res = await http.deviceApi.getList({})
  const list = (res.data || []).filter((d) => deviceSupportsEngine(d, 'web'))
  const savedList = Array.isArray(cfgDevices) ? cfgDevices : []
  const cfgMap = new Map(savedList.map((d) => [String(d.device_id), d]))
  const seen = new Set()
  const rows = list.map((d) => {
    seen.add(String(d.id))
    const saved = cfgMap.get(String(d.id))
    return {
      id: d.id,
      name: d.name,
      username: d.username,
      ip: d.ip,
      status: d.status,
      selected: !!saved,
      weight: saved?.weight || 1,
      concurrency: saved?.concurrency || 3,
    }
  })
  for (const saved of savedList) {
    const did = String(saved.device_id || '')
    if (!did || seen.has(did)) continue
    rows.push({
      id: did,
      name: did,
      username: '',
      ip: '—',
      status: '离线',
      selected: true,
      weight: saved.weight || 1,
      concurrency: saved.concurrency || 1,
    })
  }
  deviceRows.value = rows
}

/** 打开弹窗时调用：载入已有 run_config */
async function reset(config) {
  emptyLocal()
  const cfg = config && typeof config === 'object' ? config : {}
  if (cfg.browser_type) local.browser_type = cfg.browser_type
  if (typeof cfg.headless === 'boolean') local.headless = cfg.headless
  if (cfg.device_id) local.device_id = cfg.device_id
  if (typeof cfg.concurrency === 'number') local.concurrency = cfg.concurrency
  await reloadDevices(cfg.devices || [])
}

function buildPayload() {
  const selected = deviceRows.value.filter((r) => r.selected)
  const payload = {
    browser_type: local.browser_type || 'chromium',
    headless: !!local.headless,
    concurrency: local.concurrency || 1,
    devices: selected.map((r) => ({
      device_id: r.id,
      weight: r.weight || 1,
      concurrency: r.concurrency || 1,
    })),
  }
  if (local.device_id) payload.device_id = local.device_id
  return payload
}

defineExpose({ reset, buildPayload, reloadDevices })
</script>

<style scoped>
.cron-run-config__hint {
  margin-bottom: 12px;
}
.cron-run-config__table {
  width: 100%;
}
.cron-run-config__ip {
  color: #909399;
  font-size: 12px;
}
.cron-run-config__tip {
  margin-left: 8px;
  color: #909399;
  font-size: 12px;
}
</style>
