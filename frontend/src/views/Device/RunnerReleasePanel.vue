<template>
  <el-collapse v-if="loaded" v-model="activeNames" class="runner-release-panel">
    <el-collapse-item name="release">
      <template #title>
        <span class="collapse-title">
          BrickCore 执行器客户端
          <el-tag v-if="release.runner_client_version_latest" size="small" type="success" style="margin-left: 8px">
            推荐版本 v{{ release.runner_client_version_latest }}
          </el-tag>
        </span>
      </template>
    <div class="release-body">
      <p v-if="hasAnyDownload">
        <template v-if="release.external_download_available">
          <strong>推荐通过 {{ release.external_download_label || '网盘下载' }} 获取安装包</strong>（速度更快、更稳定）。
        </template>
        <template v-if="release.platform_package_available">
          若需从平台直接下载，安装包约 {{ formatSize(release.package_size_bytes) }}，下载耗时较长。
        </template>
        解压后双击 <code>BrickCoreRunner.exe</code>，登录平台账号后点击「上线」。
      </p>
      <p v-else>
        暂无可用的安装包下载。管理员可在
        <el-link type="primary" @click="goReleaseConfig">执行器发布配置</el-link>
        填写网盘链接，或将 <code>BrickCoreRunner.zip</code> 放到
        <code>{{ release.package_upload_hint || 'static/runner/' }}</code>。
        另见 <el-link type="primary" @click="goDocs('runner-client')">使用说明</el-link>。
      </p>
      <div class="release-actions">
        <el-button
          v-if="release.external_download_available"
          type="success"
          icon="Link"
          @click="openExternalDownload"
        >
          {{ release.external_download_label || '网盘下载' }}（推荐）
        </el-button>
        <el-button
          v-if="release.platform_package_available"
          type="primary"
          icon="Download"
          @click="downloadFromPlatform"
        >
          平台下载 zip
        </el-button>
        <el-button v-if="canManageRelease" link type="primary" @click="goReleaseConfig">
          配置下载地址
        </el-button>
        <el-button icon="Document" @click="goDocs('runner-client')">使用说明</el-button>
        <el-button icon="Document" @click="goDocs('runner-packaging')">打包说明</el-button>
      </div>
      <p v-if="release.platform_package_available" class="download-hint">
        平台下载由浏览器下载管理器接管，可在地址栏下方或「下载」面板查看进度、暂停或取消；切换页面或刷新本页通常不会中断下载。
      </p>
    </div>
    </el-collapse-item>
  </el-collapse>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { runnerReleaseApi } from '@/api/modules/runner'
import { UserStore } from '@/stores/module/UserStore'

const router = useRouter()
const uStore = UserStore()
const loaded = ref(false)
const activeNames = ref([])
const release = ref({
  runner_client_version_latest: '',
  package_available: false,
  package_size_bytes: 0,
  package_upload_hint: '',
  package_filename: 'BrickCoreRunner.zip',
  platform_package_available: false,
  external_download_url: '',
  external_download_available: false,
  external_download_label: '网盘下载',
})

const hasAnyDownload = computed(
  () => release.value.platform_package_available || release.value.external_download_available
)

const canManageRelease = computed(() => uStore.hasPermission('device:edit'))

const formatSize = (bytes) => {
  if (!bytes) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
}

const loadRelease = async () => {
  try {
    const res = await runnerReleaseApi.getRelease()
    if (res.status === 200 && res.data) {
      release.value = res.data
    }
  } catch {
    /* ignore */
  } finally {
    loaded.value = true
  }
}

const downloadFromPlatform = () => {
  const token = uStore.token || localStorage.getItem('token') || ''
  if (!token) {
    ElMessage.warning('请先登录平台')
    return
  }

  const url = runnerReleaseApi.downloadUrl(token)
  const filename = release.value.package_filename || 'BrickCoreRunner.zip'

  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.rel = 'noopener noreferrer'
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)

  ElMessage.success(`已开始下载 ${filename}，请在浏览器下载栏查看进度`)
}

const openExternalDownload = () => {
  const url = (release.value.external_download_url || '').trim()
  if (!url) {
    ElMessage.warning('外链地址未配置')
    return
  }
  window.open(url, '_blank', 'noopener,noreferrer')
  ElMessage.info('已在新窗口打开下载页，请按网盘提示保存 BrickCoreRunner.zip')
}

const goDocs = (docId) => {
  router.push({ path: '/docs', query: { doc: docId } })
}

const goReleaseConfig = () => {
  router.push({ path: '/runner-release-config' })
}

onMounted(loadRelease)
</script>

<style scoped>
.runner-release-panel {
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
.release-body p {
  margin: 0 0 10px;
  font-size: 13px;
  line-height: 1.6;
}
.release-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.download-hint {
  margin-top: 10px !important;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
