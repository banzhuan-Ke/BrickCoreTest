<template>
  <ConfigShell :embedded="embedded">
    <template #title>
      <b>登录页配置</b>
    </template>
    <template #main>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="配置说明"
        description="清新 Pro 推荐使用简约抽象背景（方案 1~4，默认方案 3）；经典风格独立配置。支持上传自定义图片；可配置登录页星星/光点/积木漂浮动效数量。"
        style="margin-bottom: 20px; max-width: 960px;"
      />

      <el-form :model="form" label-width="120px" style="max-width: 960px;">
        <el-form-item label="登录标题">
          <el-input v-model="form.welcome_title" maxlength="200" show-word-limit placeholder="欢迎登录 BrickCore" />
        </el-form-item>
        <el-form-item label="页脚文案">
          <el-input v-model="form.footer_text" maxlength="500" show-word-limit />
        </el-form-item>
        <el-form-item label="注册入口">
          <el-switch v-model="form.show_register" active-text="显示" inactive-text="隐藏" />
        </el-form-item>

        <el-divider content-position="left">背景漂浮动效</el-divider>
        <p class="section-tip">白色四角星、半透明光点、透明积木；鼠标经过时有轻微吸引与稀疏拖影（建议积木略多以贴合 BrickCore 主题）</p>
        <el-form-item label="启用动效">
          <el-switch v-model="form.bg_motion_enabled" active-text="开启" inactive-text="关闭" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="积木数量">
              <el-input-number
                v-model="form.bg_brick_count"
                :min="LOGIN_MOTION_LIMITS.brick.min"
                :max="LOGIN_MOTION_LIMITS.brick.max"
                controls-position="right"
                style="width: 100%;"
              />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="四角星数量">
              <el-input-number
                v-model="form.bg_star_count"
                :min="LOGIN_MOTION_LIMITS.star.min"
                :max="LOGIN_MOTION_LIMITS.star.max"
                controls-position="right"
                style="width: 100%;"
              />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="光点数量">
              <el-input-number
                v-model="form.bg_dot_count"
                :min="LOGIN_MOTION_LIMITS.dot.min"
                :max="LOGIN_MOTION_LIMITS.dot.max"
                controls-position="right"
                style="width: 100%;"
              />
            </el-form-item>
          </el-col>
        </el-row>

        <el-divider content-position="left">清新 Pro 背景</el-divider>
        <p class="section-tip">简约抽象风格，不含登录框/UI 元素，避免与真实表单重叠</p>
        <div class="bg-grid">
          <div
            v-for="opt in PRO_BG_OPTIONS"
            :key="'pro-' + opt.key"
            class="bg-card"
            :class="{ active: form.pro_bg_key === opt.key }"
            @click="selectPro(opt.key)"
          >
            <img :src="opt.asset" :alt="opt.label" />
            <div class="bg-card__meta">
              <b>{{ opt.label }}</b>
              <span>{{ opt.desc }}</span>
            </div>
            <el-icon v-if="form.pro_bg_key === opt.key" class="bg-card__check"><CircleCheckFilled /></el-icon>
          </div>
          <div
            class="bg-card bg-card--upload"
            :class="{ active: form.pro_bg_key === 'custom' }"
          >
            <div class="upload-preview" @click="form.pro_bg_key = 'custom'">
              <img v-if="form.pro_bg_url" :src="resolveStaticUrl(form.pro_bg_url)" alt="自定义 Pro" />
              <div v-else class="upload-placeholder">
                <el-icon :size="28"><UploadFilled /></el-icon>
                <span>自定义上传</span>
              </div>
            </div>
            <div class="bg-card__meta">
              <b>自定义图片</b>
              <span>上传本地背景（Pro）</span>
            </div>
            <div class="bg-card__actions" @click.stop>
              <input
                ref="proFileRef"
                type="file"
                class="hidden-file"
                accept="image/jpeg,image/png,image/webp"
                @change="(e) => handleFilePick(e, 'pro')"
              />
              <el-button size="small" type="primary" plain :loading="uploadingPro" @click="triggerFilePick('pro')">
                选择文件
              </el-button>
            </div>
            <el-icon v-if="form.pro_bg_key === 'custom'" class="bg-card__check"><CircleCheckFilled /></el-icon>
          </div>
        </div>

        <el-divider content-position="left">经典风格背景</el-divider>
        <p class="section-tip">商务稳重主题，适合经典界面与暗黑模式</p>
        <div class="bg-grid">
          <div
            v-for="opt in CLASSIC_BG_OPTIONS"
            :key="'classic-' + opt.key"
            class="bg-card"
            :class="{ active: form.classic_bg_key === opt.key }"
            @click="selectClassic(opt.key)"
          >
            <img :src="opt.asset" :alt="opt.label" />
            <div class="bg-card__meta">
              <b>{{ opt.label }}</b>
              <span>{{ opt.desc }}</span>
            </div>
            <el-icon v-if="form.classic_bg_key === opt.key" class="bg-card__check"><CircleCheckFilled /></el-icon>
          </div>
          <div
            class="bg-card bg-card--upload"
            :class="{ active: form.classic_bg_key === 'custom' }"
          >
            <div class="upload-preview" @click="form.classic_bg_key = 'custom'">
              <img v-if="form.classic_bg_url" :src="resolveStaticUrl(form.classic_bg_url)" alt="自定义经典" />
              <div v-else class="upload-placeholder">
                <el-icon :size="28"><UploadFilled /></el-icon>
                <span>自定义上传</span>
              </div>
            </div>
            <div class="bg-card__meta">
              <b>自定义图片</b>
              <span>上传本地背景（经典）</span>
            </div>
            <div class="bg-card__actions" @click.stop>
              <input
                ref="classicFileRef"
                type="file"
                class="hidden-file"
                accept="image/jpeg,image/png,image/webp"
                @change="(e) => handleFilePick(e, 'classic')"
              />
              <el-button size="small" type="primary" plain :loading="uploadingClassic" @click="triggerFilePick('classic')">
                选择文件
              </el-button>
            </div>
            <el-icon v-if="form.classic_bg_key === 'custom'" class="bg-card__check"><CircleCheckFilled /></el-icon>
          </div>
        </div>

        <el-form-item v-if="form.update_time" label="最近更新" style="margin-top: 24px;">
          <span class="meta-text">{{ form.update_by || '-' }} · {{ form.update_time }}</span>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" icon="Check" @click="saveConfig">保存配置</el-button>
          <el-button icon="Refresh" @click="loadConfig">刷新</el-button>
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
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { loginPageApi } from '@/api/modules/sys.js'
import {
  PRO_BG_OPTIONS,
  CLASSIC_BG_OPTIONS,
  LOGIN_PAGE_DEFAULTS,
  LOGIN_MOTION_LIMITS,
  resolveStaticUrl,
} from '@/constants/loginPageBackgrounds.js'
import { useLoginPageConfig } from '@/composables/useLoginPageConfig.js'

const { invalidateLoginPageConfigCache } = useLoginPageConfig()

const proFileRef = ref(null)
const classicFileRef = ref(null)
const uploadingPro = ref(false)
const uploadingClassic = ref(false)

const form = reactive({
  ...LOGIN_PAGE_DEFAULTS,
  update_by: '',
  update_time: '',
})

function selectPro(key) {
  form.pro_bg_key = key
}

function selectClassic(key) {
  form.classic_bg_key = key
}

function resolveConfigLoadMessage(error) {
  const status = error?.status ?? error?.response?.status
  const code = error?.code
  const detail = error?.data?.detail ?? error?.response?.data?.detail
  const msg = String(error?.message ?? '')

  if (code === 'ECONNABORTED' || /timeout/i.test(msg)) {
    return '获取登录页配置超时，请检查后端服务是否正常（与数据库迁移无关）'
  }
  if (code === 'ERR_NETWORK' || /Network Error/i.test(msg)) {
    return '无法连接后端，请检查网络或 Docker 中 backend 是否运行'
  }
  if (status === 401) return '登录已过期，请重新登录后再试'
  if (status === 403) return '无登录页配置权限（login_page_config:view），请联系管理员分配'
  if (status === 404) return '登录页配置接口不存在，请拉取最新代码并重启 backend'
  if (typeof detail === 'string' && /migration|column|字段|表|Unknown/i.test(detail)) {
    return `数据库结构可能未更新：${detail}`
  }
  if (typeof detail === 'string' && detail) return detail
  return '加载配置失败，已使用本地默认值'
}

const loadConfig = async () => {
  try {
    const res = await loginPageApi.getConfig()
    const data = res?.data ?? res ?? {}
    if (res?.status && res.status >= 400) {
      throw res
    }
    Object.assign(form, LOGIN_PAGE_DEFAULTS, data)
  } catch (error) {
    console.error(error)
    Object.assign(form, LOGIN_PAGE_DEFAULTS)
    ElMessage.warning(resolveConfigLoadMessage(error))
  }
}

const saveConfig = async () => {
  if (form.pro_bg_key === 'custom' && !form.pro_bg_url) {
    ElMessage.warning('请先上传 Pro 自定义背景，或选择内置方案')
    return
  }
  if (form.classic_bg_key === 'custom' && !form.classic_bg_url) {
    ElMessage.warning('请先上传经典自定义背景，或选择内置方案')
    return
  }
  try {
    const res = await loginPageApi.updateConfig({
      pro_bg_key: form.pro_bg_key,
      classic_bg_key: form.classic_bg_key,
      pro_bg_url: form.pro_bg_url,
      classic_bg_url: form.classic_bg_url,
      welcome_title: form.welcome_title,
      footer_text: form.footer_text,
      show_register: form.show_register,
      bg_brick_count: form.bg_brick_count,
      bg_star_count: form.bg_star_count,
      bg_dot_count: form.bg_dot_count,
      bg_motion_enabled: form.bg_motion_enabled,
    })
    const data = res?.data ?? res ?? {}
    Object.assign(form, data)
    invalidateLoginPageConfigCache()
    ElMessage.success('登录页配置已保存')
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error?.data?.detail || '保存失败')
  }
}

function triggerFilePick(theme) {
  if (theme === 'pro') {
    proFileRef.value?.click()
  } else {
    classicFileRef.value?.click()
  }
}

async function handleFilePick(event, theme) {
  const input = event.target
  const file = input?.files?.[0]
  if (input) input.value = ''
  if (!file) return

  const allowed = ['image/jpeg', 'image/png', 'image/webp']
  if (!allowed.includes(file.type)) {
    ElMessage.error('仅支持 jpg/png/webp')
    return
  }
  if (file.size > 5 * 1024 * 1024) {
    ElMessage.error('图片不能超过 5MB')
    return
  }

  const loadingRef = theme === 'pro' ? uploadingPro : uploadingClassic
  loadingRef.value = true
  try {
    const res = await loginPageApi.uploadBackground(file, theme)
    const body = res?.data ?? res
    const url = body?.url ?? body?.data?.url
    if (!url) {
      ElMessage.error('上传失败：未返回图片地址')
      return
    }
    if (theme === 'pro') {
      form.pro_bg_key = 'custom'
      form.pro_bg_url = url
    } else {
      form.classic_bg_key = 'custom'
      form.classic_bg_url = url
    }
    ElMessage.success('上传成功，请点击「保存配置」生效')
  } catch (error) {
    const detail = error?.data?.detail ?? error?.response?.data?.detail ?? '上传失败'
    ElMessage.error(typeof detail === 'string' ? detail : '上传失败')
  } finally {
    loadingRef.value = false
  }
}

onMounted(() => {
  loadConfig()
})
</script>

<style scoped lang="scss">
.section-tip {
  margin: -4px 0 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.bg-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 14px;
  margin-bottom: 20px;
}

.bg-card {
  position: relative;
  border: 2px solid var(--el-border-color-light);
  border-radius: 12px;
  overflow: hidden;
  cursor: pointer;
  transition: all 0.2s ease;
  background: #fff;

  &:hover {
    border-color: var(--el-color-primary-light-5);
    box-shadow: 0 8px 24px rgba(75, 111, 255, 0.12);
  }

  &.active {
    border-color: var(--el-color-primary);
    box-shadow: 0 10px 28px rgba(75, 111, 255, 0.18);
  }

  img {
    width: 100%;
    height: 112px;
    object-fit: cover;
    display: block;
  }

  &__meta {
    padding: 10px 12px 12px;
    display: flex;
    flex-direction: column;
    gap: 4px;

    b {
      font-size: 13px;
      color: var(--el-text-color-primary);
    }

    span {
      font-size: 11px;
      color: var(--el-text-color-secondary);
      line-height: 1.4;
    }
  }

  &__check {
    position: absolute;
    top: 8px;
    right: 8px;
    font-size: 22px;
    color: var(--el-color-primary);
    filter: drop-shadow(0 1px 2px rgba(255, 255, 255, 0.9));
  }

  &--upload {
    .upload-preview {
      height: 112px;
      background: var(--el-fill-color-light);
      display: flex;
      align-items: center;
      justify-content: center;

      img {
        height: 100%;
      }
    }

    .upload-placeholder {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 6px;
      color: var(--el-text-color-secondary);
      font-size: 12px;
    }

    .bg-card__actions {
      padding: 0 12px 12px;
    }

    .hidden-file {
      display: none;
    }
  }
}

.bg-card--upload {
  cursor: default;
}

.meta-text {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
</style>
