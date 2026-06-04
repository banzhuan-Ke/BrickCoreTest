<template>
  <div class="device-info-wrapper">
    <!-- 顶部状态栏 -->
    <div class="status-bar">
      <div class="status-left">
        <div class="status-item">
          <div :class="['status-dot', isConnected ? '' : 'offline']"/>
          <div>
            <div class="status-label">设备编号</div>
            <div class="status-value">{{ deviceDetail.id || '-' }}</div>
          </div>
        </div>
        <div class="status-item">
          <div :class="['status-dot', isConnected ? '' : 'offline']"/>
          <div>
            <div class="status-label">设备 IP</div>
            <div class="status-value">{{ deviceDetail.ip || '-' }}</div>
          </div>
        </div>
        <div class="status-item">
          <div :class="['status-dot', isConnected ? '' : 'offline']"/>
          <div>
            <div class="status-label">操作系统</div>
            <div class="status-value">{{ deviceDetail.system || '-' }}</div>
          </div>
        </div>
        <div class="status-item">
          <div :class="['status-dot', isConnected ? '' : 'offline']"/>
          <div>
            <div class="status-label">设备名称</div>
            <div class="status-value">{{ deviceDetail.name || '-' }}</div>
          </div>
        </div>
      </div>
      <div class="status-right">
        <div :class="['connection-badge', isConnected ? '' : 'disconnected']">
          <el-icon v-if="isConnected" size="12"><CircleCheck /></el-icon>
          <el-icon v-else size="12"><CircleClose /></el-icon>
          {{ isConnected ? '已连接' : '未连接' }}
        </div>
      </div>
    </div>

    <!-- 主内容区 -->
    <div class="monitor-layout">
      <!-- 屏幕区域 -->
      <div class="screen-section">
        <div class="section-header">
          <div class="header-title">
            <el-icon size="16"><Monitor /></el-icon>
            <span>执行机屏幕监控</span>
          </div>
          <div class="header-actions">
            <el-button
              link
              type="primary"
              size="small"
              :icon="FullScreen"
              @click="toggleFullscreen"
            >
              全屏
            </el-button>
          </div>
        </div>
        <div :class="['screen-canvas', screenLoading ? 'loading' : '']">
          <div v-if="!hasLiveScreen" class="screen-placeholder">
            <el-icon :size="36"><Monitor /></el-icon>
            <span>等待执行机画面…</span>
            <span class="screen-placeholder-hint">设备上线后约 2 秒内刷新；执行用例时实时更新</span>
          </div>
          <img
            id="screen"
            :src="screenSrc"
            alt="Device Screen"
            class="screen-image"
            :class="{ 'is-live': hasLiveScreen }"
            @load="onScreenLoad"
          />
        </div>
      </div>

      <!-- 日志区域 -->
      <div class="log-section">
        <div class="section-header">
          <div class="header-title">
            <el-icon size="16"><Document /></el-icon>
            <span>执行日志</span>
          </div>
          <el-button
            link
            type="danger"
            size="small"
            :icon="Delete"
            @click="clearLogs"
          >
            清空
          </el-button>
        </div>
        <div id="logs-container" class="log-terminal">
          <div v-if="logs.length === 0" class="terminal-empty">
            <el-icon size="28" color="rgba(255,255,255,0.1)"><Document /></el-icon>
            <div>等待执行日志...</div>
          </div>
          <div
            v-for="(log, index) in logs"
            :key="index"
            class="terminal-line"
          >
            <span class="line-time">{{ log.time }}</span>
            <span class="line-index">{{ String(index + 1).padStart(3, '0') }}</span>
            <span :class="['line-text', 'level-' + log.level]">{{ log.message }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch, computed } from 'vue'
import http from '@/api/index'
import {
  Monitor,
  Document,
  Delete,
  CircleCheck,
  CircleClose,
  FullScreen
} from '@element-plus/icons-vue'

// 定义 props
const props = defineProps({
  deviceId: {
    type: String,
    required: true
  }
})

// 响应式数据
const logs = ref([])
const screenLoading = ref(false)
const hasLiveScreen = ref(false)

// 设备在线状态（以后端 status 为准，和列表页保持一致）
const isConnected = computed(() => {
  const s = deviceDetail.value.status
  return s === '在线' || s === '执行中'
})

// 设备详情
const deviceDetail = ref({
  id: '',
  name: '',
  ip: '',
  system: ''
})

// 默认图片 URL
const screenSrc = ref(new URL('@/assets/images/device.jpg', import.meta.url).href)

// WebSocket实例
let ws

// 获取当前时间 HH:mm:ss
const getTimeStr = () => {
  const now = new Date()
  return String(now.getHours()).padStart(2, '0') + ':' +
         String(now.getMinutes()).padStart(2, '0') + ':' +
         String(now.getSeconds()).padStart(2, '0')
}

// 解析日志级别
const parseLogLevel = (msg) => {
  if (msg.includes('ERROR') || msg.includes('错误') || msg.includes('失败')) return 'error'
  if (msg.includes('WARN') || msg.includes('警告')) return 'warn'
  if (msg.includes('SUCCESS') || msg.includes('成功') || msg.includes('通过')) return 'success'
  return 'info'
}

// 清空日志
const clearLogs = () => {
  logs.value = []
}

const onScreenLoad = () => {
  screenLoading.value = false
  if (screenSrc.value && !screenSrc.value.includes('device.jpg')) {
    hasLiveScreen.value = true
  }
}

// 全屏
const toggleFullscreen = () => {
  const img = document.getElementById('screen')
  if (img) {
    if (document.fullscreenElement) {
      document.exitFullscreen()
    } else {
      img.requestFullscreen()
    }
  }
}

// 处理消息
const handleMessage = (event) => {
  try {
    const message = JSON.parse(event.data)
    if (message.type === 'log') {
      if (!message.data) return
      logs.value.push({
        time: getTimeStr(),
        level: parseLogLevel(message.data),
        message: message.data
      })
      // 自动滚动到日志底部
      const logsContainer = document.getElementById('logs-container')
      if (logsContainer) {
        logsContainer.scrollTop = logsContainer.scrollHeight
      }
    } else if (message.type === 'screen') {
      if (!message.data) return
      const fmt = (message.format || 'jpeg').replace('jpg', 'jpeg')
      screenLoading.value = true
      hasLiveScreen.value = true
      screenSrc.value = `data:image/${fmt};base64,${message.data}`
    }
  } catch (e) {
    console.warn('[Device] 收到非 JSON 消息:', event.data)
  }
}

// 设置WebSocket连接
const setupWebSocket = () => {
  if (ws) {
    ws.close()
  }
  logs.value = []
  hasLiveScreen.value = false
  const wsUrl = `${import.meta.env.VITE_BASE_WS}/sys/devices/ws/${props.deviceId}`
  ws = new WebSocket(wsUrl)
  ws.onmessage = handleMessage
  ws.onclose = () => {}
  ws.onerror = () => {}
}

// 监听props.deviceId的变化
watch(() => props.deviceId, () => {
  setupWebSocket()
})

// 获取设备详情方法
const getDeviceDetail = async () => {
  const response = await http.deviceApi.getDeviceDetail(props.deviceId)
  if (response.data) {
    deviceDetail.value = { ...response.data }
  }
}

// 生命周期钩子
onMounted(async () => {
  await getDeviceDetail()
  setupWebSocket()
})

// 清理WebSocket连接
onUnmounted(() => {
  if (ws) {
    ws.close()
  }
})
</script>

<style scoped lang="scss">
@use "./DeviceInfo.scss";
</style>
