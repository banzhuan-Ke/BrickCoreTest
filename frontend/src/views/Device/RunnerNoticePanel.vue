<template>
  <el-collapse v-if="loaded && notices" class="runner-notice-panel" v-model="activeNames">
    <el-collapse-item name="runtime">
      <template #title>
        <span class="collapse-title">
          <el-icon><InfoFilled /></el-icon>
          Runner 运行要求与注意事项
          <el-tag size="small" type="success" style="margin-left: 8px">v{{ notices.version || release.runner_client_version_latest }}</el-tag>
        </span>
      </template>
      <div class="notice-section">
        <h4>安装包模式（测试机）</h4>
        <ul>
          <li v-for="(item, i) in notices.runtime_requirements" :key="'r' + i">{{ item }}</li>
        </ul>
        <p v-if="outdatedDevices.length" class="outdated-hint">
          <el-icon color="#e6a23c"><WarningFilled /></el-icon>
          有 {{ outdatedDevices.length }} 台设备客户端版本低于推荐 v{{ release.runner_client_version_latest }}，请重新下载安装包。
        </p>
      </div>
    </el-collapse-item>

    <el-collapse-item name="recording">
      <template #title>
        <span class="collapse-title">
          <el-icon><VideoCamera /></el-icon>
          UI 录制提示（v1.3.6+）
        </span>
      </template>
      <ul>
        <li v-for="(item, i) in notices.recording_tips" :key="'t' + i">{{ item }}</li>
      </ul>
    </el-collapse-item>

    <el-collapse-item name="troubleshoot">
      <template #title>
        <span class="collapse-title">
          <el-icon><Tools /></el-icon>
          常见问题排查
        </span>
      </template>
      <el-collapse accordion class="inner-faq">
        <el-collapse-item
          v-for="(item, i) in notices.troubleshooting"
          :key="'f' + i"
          :title="item.title"
          :name="String(i)"
        >
          <p>{{ item.detail }}</p>
        </el-collapse-item>
      </el-collapse>
      <div class="doc-links">
        <el-button size="small" icon="Document" @click="goDocs('runner-client')">使用说明</el-button>
        <el-button size="small" icon="Document" @click="goDocs('runner-packaging')">打包说明</el-button>
        <el-button size="small" icon="Document" @click="goDocs('runner-troubleshooting')">排查指南</el-button>
      </div>
    </el-collapse-item>
  </el-collapse>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { InfoFilled, WarningFilled, VideoCamera, Tools } from '@element-plus/icons-vue'
import { runnerReleaseApi } from '@/api/modules/runner'
import { ProjectStore } from '@/stores/module/ProjectStore'

const props = defineProps({
  release: {
    type: Object,
    default: () => ({}),
  },
})

const router = useRouter()
const proStore = ProjectStore()
const loaded = ref(false)
const localRelease = ref({})
const activeNames = ref([])

const release = computed(() => ({
  ...localRelease.value,
  ...props.release,
}))

const notices = computed(() => release.value.runner_notices || null)

const outdatedDevices = computed(() => {
  const latest = release.value.runner_client_version_latest || notices.value?.version || ''
  if (!latest) return []
  return (proStore.deviceList || []).filter(d => {
    const v = d.runner_client_version || ''
    return v && compareVersion(v, latest) < 0
  })
})

function parseVersion(version) {
  return (version || '0').split('.').map(s => parseInt(s.split('-')[0], 10) || 0)
}

function compareVersion(left, right) {
  const a = parseVersion(left)
  const b = parseVersion(right)
  const len = Math.max(a.length, b.length)
  for (let i = 0; i < len; i++) {
    const x = a[i] || 0
    const y = b[i] || 0
    if (x > y) return 1
    if (x < y) return -1
  }
  return 0
}

const goDocs = (docId) => {
  router.push({ path: '/docs', query: { doc: docId } })
}

const loadRelease = async () => {
  try {
    const res = await runnerReleaseApi.getRelease()
    if (res.status === 200 && res.data) {
      localRelease.value = res.data
    }
  } finally {
    loaded.value = true
  }
}

onMounted(loadRelease)
</script>

<style scoped>
.runner-notice-panel {
  margin-bottom: 16px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  overflow: hidden;
}
.collapse-title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-weight: 500;
}
.notice-section h4 {
  margin: 8px 0 4px;
  font-size: 13px;
  color: var(--el-text-color-primary);
}
.notice-section ul,
.runner-notice-panel > :deep(.el-collapse-item) ul {
  margin: 0 0 8px;
  padding-left: 20px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--el-text-color-regular);
}
.outdated-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 8px 0 0;
  padding: 8px 10px;
  background: #fdf6ec;
  border-radius: 6px;
  font-size: 13px;
  color: #e6a23c;
}
.inner-faq {
  border: none;
}
.doc-links {
  margin-top: 10px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
</style>
