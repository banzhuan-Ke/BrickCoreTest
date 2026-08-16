<template>
  <ConfigShell :embedded="embedded">
    <template #title>
      <b>执行器发布配置</b>
    </template>
    <template #main>
      <el-alert type="info" :closable="false" show-icon class="hint-alert">
        <template #title>大安装包（约 800MB）建议放网盘/OSS</template>
        在此填写外链后，设备管理页会显示「网盘下载」按钮；也可继续将 zip 放到服务器
        <code>static/runner/</code> 使用「平台下载」。环境变量 <code>RUNNER_CLIENT_DOWNLOAD_URL</code> 在未保存平台配置时作为兜底。
        精简压测包 <code>BrickCorePerf.zip</code> / <code>BrickCorePerf-mac.zip</code> 同目录上传后即可被平台检测。
      </el-alert>

      <el-form :model="form" label-width="160px" style="max-width: 800px; margin-top: 16px">
        <el-form-item label="网盘/OSS 链接：">
          <el-input
            v-model="form.external_download_url"
            placeholder="https://pan.baidu.com/... 或 OSS 直链"
            clearable
          />
          <div class="field-hint">分享页或 HTTPS 直链均可；客户端「检查更新」会优先使用该地址</div>
        </el-form-item>
        <el-form-item label="按钮文案：">
          <el-input v-model="form.external_download_label" placeholder="网盘下载" maxlength="20" />
        </el-form-item>
        <el-form-item label="完整执行器：">
          <span v-if="form.platform_package_available">
            已就绪（{{ formatSize(form.platform_package_size_bytes) }}）
          </span>
          <span v-else class="text-muted">未上传 — 将 BrickCoreRunner.zip 放到 static/runner/</span>
        </el-form-item>
        <el-form-item label="分层增量包：">
          <div v-if="form.update_patches_available && (form.update_channels || []).length">
            <div v-for="ch in form.update_channels" :key="ch.id" class="patch-row">
              <el-tag size="small" :type="ch.available ? 'success' : 'info'">{{ ch.id }}</el-tag>
              <span>{{ ch.filename || '-' }} · {{ formatSize(ch.size) }}</span>
              <span v-if="!ch.available" class="text-muted">（清单有记录但文件缺失）</span>
            </div>
          </div>
          <span v-else class="text-muted">
            未上传 — 将 dist/patches/* 放到 static/runner/patches/（含 update_manifest.json）
          </span>
          <div class="field-hint">正式打包会生成加密 .bcpack；客户端优先增量更新，底座变更仍用整包</div>
        </el-form-item>
        <el-form-item label="精简压测包 Win：">
          <span v-if="form.perf_package_available">
            已就绪（{{ formatSize(form.perf_package_size_bytes) }}）
          </span>
          <span v-else class="text-muted">未上传 — 将 BrickCorePerf.zip 放到 static/runner/</span>
        </el-form-item>
        <el-form-item label="精简压测包 Mac：">
          <span v-if="form.perf_package_mac_available">
            已就绪（{{ formatSize(form.perf_package_mac_size_bytes) }}）
          </span>
          <span v-else class="text-muted">未上传 — 将 BrickCorePerf-mac.zip 放到 static/runner/</span>
        </el-form-item>
        <el-form-item v-if="form.using_env_fallback" label="当前来源：">
          <el-tag type="warning" size="small">环境变量兜底</el-tag>
          <span class="field-hint" style="margin-left: 8px">保存后将使用下方平台配置</span>
        </el-form-item>
        <el-form-item v-if="form.update_time" label="最近更新：">
          <span class="meta-text">{{ form.update_by || '-' }} · {{ form.update_time }}</span>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="saveConfig" icon="Check">保存</el-button>
          <el-button @click="loadConfig" icon="Refresh">刷新</el-button>
        </el-form-item>
      </el-form>
    </template>
  </ConfigShell>
</template>

<script setup>
import ConfigShell from '@/components/ConfigShell.vue'

defineProps({
  embedded: { type: Boolean, default: false }
})

import { reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { runnerReleaseApi } from '@/api/modules/runner'

const form = reactive({
  external_download_url: '',
  external_download_label: '网盘下载',
  platform_package_available: false,
  platform_package_size_bytes: 0,
  perf_package_available: false,
  perf_package_size_bytes: 0,
  perf_package_mac_available: false,
  perf_package_mac_size_bytes: 0,
  update_channels: [],
  update_patches_available: false,
  update_patches_hint: '',
  using_env_fallback: false,
  update_by: '',
  update_time: ''
})

const formatSize = (bytes) => {
  if (!bytes) return '0 B'
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
}

const loadConfig = async () => {
  try {
    const res = await runnerReleaseApi.getConfig()
    if (res.status === 200 && res.data) {
      Object.assign(form, res.data)
    }
  } catch (e) {
    if (e?.code === 'ECONNABORTED' || /timeout/i.test(String(e?.message || ''))) {
      ElMessage.error('获取发布配置超时（可能数据库繁忙或刚上传大包）。请稍后刷新；可用服务器 ls 确认 zip/patches 是否已在')
    } else {
      ElMessage.error(e?.response?.data?.detail || '获取配置失败')
    }
  }
}

const saveConfig = async () => {
  try {
    const res = await runnerReleaseApi.updateConfig({
      external_download_url: form.external_download_url,
      external_download_label: form.external_download_label || '网盘下载'
    })
    if (res.status === 200 && res.data) {
      Object.assign(form, res.data)
      ElMessage.success('已保存，设备管理页下载入口立即生效')
    }
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  }
}

onMounted(loadConfig)
</script>

<style scoped>
.hint-alert {
  margin-bottom: 8px;
}
.field-hint {
  font-size: 12px;
  color: #909399;
  line-height: 1.5;
  margin-top: 4px;
}
.meta-text {
  font-size: 13px;
  color: #606266;
}
.text-muted {
  color: #909399;
}
.patch-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
  font-size: 13px;
}
</style>
