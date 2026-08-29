<template>
  <PageCard>
    <template #title>
      <b>设备管理</b>
    </template>
    <template #main>
      <RunnerReleasePanel />
      <RunnerNoticePanel />
      <el-table :data="proStore.deviceList" :header-cell-style="{'text-align':'center'}"
                :cell-style="{'text-align':'center'}" stripe>
        <template #empty>
          <div class="table-empty">
            <div class="empty-icon">
              <el-icon :size="40" color="#909399"><Monitor /></el-icon>
            </div>
            <div>暂无数据</div>
          </div>
        </template>
        <el-table-column label="序号" type="index" width="80"/>
        <el-table-column label="设备编号" prop="id" width="150">
          <template #default="scope">
            <span>{{ scope.row.id }}</span>
            <el-button link type="primary" size="small" @click="copyText(scope.row.id)">复制</el-button>
          </template>
        </el-table-column>
        <el-table-column label="设备名称" prop="name"/>
        <el-table-column label="客户端版本" prop="runner_client_version" width="120">
          <template #default="scope">
            <template v-if="scope.row.runner_client_version">
              <span>v{{ scope.row.runner_client_version }}</span>
              <el-tag v-if="isOutdatedClient(scope.row.runner_client_version)" size="small" type="warning" style="margin-left: 4px">需升级</el-tag>
            </template>
            <span v-else class="text-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="引擎能力" width="120">
          <template #default="scope">
            <el-tag
              v-for="t in normalizeEngineTypes(scope.row)"
              :key="t"
              size="small"
              :type="t === 'app' ? 'success' : 'info'"
              style="margin: 2px"
            >
              {{ engineTypeLabel(t) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="App UDID" min-width="160" show-overflow-tooltip>
          <template #default="scope">
            <template v-if="scope.row.app_udid">
              <span>{{ scope.row.app_udid }}</span>
              <el-tag v-if="scope.row.app_connection" size="small" type="info" style="margin-left: 4px">
                {{ scope.row.app_connection }}
              </el-tag>
            </template>
            <span v-else class="text-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="工具链" width="180">
          <template #default="scope">
            <template v-if="toolchainTags(scope.row).length">
              <el-tag
                v-for="item in toolchainTags(scope.row)"
                :key="item.key"
                size="small"
                :type="item.ok ? 'success' : 'danger'"
                style="margin: 2px"
              >
                {{ item.key }}
              </el-tag>
            </template>
            <span v-else class="text-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="最后心跳" prop="runner_last_heartbeat" width="160">
          <template #default="scope">
            <span v-if="scope.row.runner_last_heartbeat">
              {{ dateTools.rTime(scope.row.runner_last_heartbeat) }}
            </span>
            <span v-else class="text-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="操作系统" prop="system">
          <template #default="scope">
            <el-tag v-if='scope.row.system==="Windows"' type="success">Windows</el-tag>
            <el-tag v-else-if='scope.row.system==="Linux"' type="warning">Linux</el-tag>
            <el-tag v-else-if='scope.row.system==="MacOS"' type="info">MacOS</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="主机名" prop="hostname" min-width="150"/>
        <el-table-column label="系统版本" prop="version" show-overflow-tooltip width="100"/>
        <el-table-column label="执行人" prop="username"/>
        <el-table-column label="设备IP" prop="ip" width="120"/>
        <el-table-column label="状态" prop="status">
          <template #default="scope">
            <el-tag v-if='scope.row.status==="离线"' type="info">离线</el-tag>
            <el-tag v-else-if='scope.row.status==="在线"' type="success">在线</el-tag>
            <el-tag v-else-if='scope.row.status==="已停止"' type="warning">已停止</el-tag>
            <el-tag v-else-if='scope.row.status==="执行中"' type="primary">执行中</el-tag>
            <el-tag v-else-if='scope.row.status==="故障"' type="danger">故障</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" prop="create_time" min-width="150">
          <template #default="scope">
            {{ dateTools.rTime(scope.row.create_time) }}
          </template>
        </el-table-column>
        <el-table-column label="更新时间" min-width="150">
          <template #default="scope">
            {{ dateTools.rTime(scope.row.update_time) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="320">
          <template #default="scope">
            <el-button plain type="success" @click="clickDeviceInfo(scope.row)" icon="View">实时画面</el-button>
            <el-button
              v-if="scope.row.status === '在线' || scope.row.status === '执行中'"
              plain
              type="warning"
              @click="stopDevice(scope.row)"
              icon="VideoPause"
            >
              停止
            </el-button>
            <el-button plain type="danger" @click="deleteDevice(scope.row.id)" icon="Delete">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </template>
  </PageCard>
  <!--  显示设备详情的弹框-->
  <el-dialog v-model="showDeviceDlg" title="WEB自动化实时画面" width="95%" center style="font-weight: bold" destroy-on-close>
    <DeviceInfo :device-id="deviceId" :key="deviceId"></DeviceInfo>
  </el-dialog>
</template>

<script setup>
import {ref, onMounted, onUnmounted} from 'vue'
import {Monitor, VideoPause} from "@element-plus/icons-vue"
import http from '@/api/index'
import { runnerReleaseApi } from '@/api/modules/runner'
import DeviceInfo from "@/views/Device/DeviceInfo.vue"
import RunnerReleasePanel from "@/views/Device/RunnerReleasePanel.vue"
import RunnerNoticePanel from "@/views/Device/RunnerNoticePanel.vue"
import {ProjectStore} from "@/stores/module/ProjectStore.js"
import {ElMessage, ElMessageBox, ElNotification} from "element-plus"
import PageCard from "@/components/PageCard.vue"
import dateTools from "@/tools/dateTools.js";

const proStore = ProjectStore()
const recommendedClientVersion = ref('')

function parseClientVersion(version) {
  return (version || '0').split('.').map(s => parseInt(s.split('-')[0], 10) || 0)
}

function compareClientVersion(left, right) {
  const a = parseClientVersion(left)
  const b = parseClientVersion(right)
  const len = Math.max(a.length, b.length)
  for (let i = 0; i < len; i++) {
    const x = a[i] || 0
    const y = b[i] || 0
    if (x > y) return 1
    if (x < y) return -1
  }
  return 0
}

const isOutdatedClient = (version) => {
  if (!version || !recommendedClientVersion.value) return false
  return compareClientVersion(version, recommendedClientVersion.value) < 0
}

function normalizeEngineTypes(row) {
  const types = row?.runner_engine_types
  if (Array.isArray(types) && types.length) return types
  return ['web']
}

function engineTypeLabel(type) {
  const map = { web: 'Web', app: 'App', perf: '压测' }
  return map[type] || type
}

function toolchainTags(row) {
  const ts = row?.toolchain_status || {}
  const tags = []
  if (ts.browser_use === 'ok') tags.push({ key: 'browser-use', ok: true })
  else if (ts.browser_use === 'missing') tags.push({ key: 'browser-use', ok: false })
  if (ts.web === 'ok') tags.push({ key: 'web', ok: true })
  else if (ts.web === 'missing') tags.push({ key: 'web', ok: false })
  if (ts.adb === 'ok') tags.push({ key: 'adb', ok: true })
  else if (ts.adb === 'missing') tags.push({ key: 'adb', ok: false })
  if (ts.uiautomator2 === 'ok') tags.push({ key: 'u2', ok: true })
  else if (ts.uiautomator2 === 'missing') tags.push({ key: 'u2', ok: false })
  return tags
}

function copyText(text) {
  navigator.clipboard.writeText(String(text)).then(() => {
    ElMessage.success('已复制')
  }).catch(() => {
    ElMessage.error('复制失败')
  })
}

// -----------------------------设备列表------------------------
// 页面加载时获取设备列表
proStore.getDeviceList()

// 定时刷新设备列表（每3秒）
let refreshInterval = null
onMounted(() => {
  runnerReleaseApi.getRelease().then(res => {
    if (res.status === 200 && res.data?.runner_client_version_latest) {
      recommendedClientVersion.value = res.data.runner_client_version_latest
    }
  }).catch(() => {})
  refreshInterval = setInterval(() => {
    proStore.getDeviceList()
  }, 3000)
})

onUnmounted(() => {
  if (refreshInterval) {
    clearInterval(refreshInterval)
  }
})

// ==========================设备详情===========================

// 选中的设备
const deviceId = ref(null)
const showDeviceDlg = ref(false)
const clickDeviceInfo = async (device) => {
  showDeviceDlg.value = true
  deviceId.value = device.id
}

// =============停止设备=======================
const stopDevice = async (device) => {
  ElMessageBox.confirm(
    `确定停止设备「${device.name}」吗？停止后将不再接收任务与上报画面/日志，需在 Runner 客户端重新点击「上线」才能恢复。`,
    '停止 Runner',
    {
      confirmButtonText: '确定停止',
      cancelButtonText: '取消',
      center: true,
      type: 'warning',
    }
  ).then(async () => {
    const response = await http.deviceApi.stop(device.id)
    if (response.status === 200) {
      ElNotification({
        type: 'success',
        title: '设备已停止',
        message: response.data?.message || 'Runner 需重新上线后方可使用',
        duration: 2500,
      })
      await proStore.getDeviceList()
    }
  }).catch(() => {})
}

// =============删除设备=======================
const deleteDevice = async (deviceId) => {
  //二次确认删除
  ElMessageBox.confirm(
      '此操作不可恢复，确定要删除该设备吗？',
      '提示', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        center: true,
        type: 'warning'
      })
      .then(async () => {
        const response = await http.deviceApi.deleteDevice(deviceId)
        if (response.status === 204) {
          ElNotification({
            type: 'success',
            title: '设备删除成功！',
            duration: 1500
          })
          // 删除成功后重新获取设备列表
          await proStore.getDeviceList()
        } else {
          ElNotification({
            type: 'error',
            title: '设备删除失败！',
            duration: 1500,
            message: response.data.detail
          })
        }
      })
      .catch(() => {
        ElMessage({
          type: 'info',
          message: '已取消删除操作。',
          duration: 1500,
        })
      })
}
</script>

<style scoped>
.text-muted {
  color: #909399;
}
</style>

<style scoped>
</style>