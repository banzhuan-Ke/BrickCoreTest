<template>
  <PageCard>
    <template #title>
      <b>平台配置</b>
    </template>
    <template #main>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="全站统一配置"
        description="本页仅包含平台级配置（AI 模型、SMTP、MCP、执行器、登录页等）。自愈 / AI Act / 功能用例软区间 / 项目通知渠道请到「项目配置 → 项目设置」。"
        style="margin-bottom: 16px;"
      />
      <el-tabs v-model="activeTab" type="border-card" @tab-change="onTabChange">
        <el-tab-pane v-if="canTab('ai')" label="AI 模型" name="ai" lazy>
          <AiConfig embedded />
        </el-tab-pane>
        <el-tab-pane v-if="canTab('smtp')" label="邮件 SMTP" name="notify" lazy>
          <SmtpConfig embedded />
        </el-tab-pane>
        <el-tab-pane v-if="canTab('mcp')" label="MCP Server" name="mcp" lazy>
          <McpConfig embedded />
        </el-tab-pane>
        <el-tab-pane v-if="canTab('runner')" label="执行器发布" name="runner" lazy>
          <RunnerReleaseConfig embedded />
        </el-tab-pane>
        <el-tab-pane v-if="canTab('login')" label="登录页" name="login" lazy>
          <LoginPageConfig embedded />
        </el-tab-pane>
        <el-tab-pane v-if="canTab('data')" label="数据保留" name="data" lazy>
          <DataRetentionConfig embedded />
        </el-tab-pane>
        <el-tab-pane v-if="canTab('streamParser')" label="SSE 解析配置" name="stream-parser" lazy>
          <StreamParserConfig embedded />
        </el-tab-pane>
      </el-tabs>
      <el-empty v-if="!hasAnyTab" description="当前账号无平台配置相关权限" />
    </template>
  </PageCard>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PageCard from '@/components/PageCard.vue'
import { UserStore } from '@/stores/module/UserStore'
import AiConfig from '@/views/AI/AiConfig.vue'
import SmtpConfig from '@/views/System/SmtpConfig.vue'
import McpConfig from '@/views/System/McpConfig.vue'
import RunnerReleaseConfig from '@/views/System/RunnerReleaseConfig.vue'
import LoginPageConfig from '@/views/System/LoginPageConfig.vue'
import DataRetentionConfig from '@/views/System/DataRetentionConfig.vue'
import StreamParserConfig from '@/views/System/StreamParserConfig.vue'

const TAB_PERMISSIONS = {
  ai: 'ai_config:view',
  smtp: 'smtp_config:view',
  mcp: 'mcp_config:view',
  runner: 'device:edit',
  login: 'login_page_config:view',
  data: 'platform_settings:view',
  streamParser: 'ai_config:view',
}

const TOP_TAB_ALIASES = {
  'ai-config': 'ai',
  smtp: 'notify',
  'smtp-config': 'notify',
  notify: 'notify',
  mcp: 'mcp',
  'mcp-config': 'mcp',
  runner: 'runner',
  'runner-release-config': 'runner',
  login: 'login',
  'login-page-config': 'login',
  data: 'data',
  'data-retention': 'data',
  'platform-settings': 'data',
  'stream-parser': 'stream-parser',
  'stream-parser-config': 'stream-parser',
}

const route = useRoute()
const router = useRouter()
const uStore = UserStore()

const activeTab = ref('ai')

const canTab = (key) => {
  const perm = TAB_PERMISSIONS[key]
  return perm ? uStore.hasPermission(perm) : false
}

const hasAnyTab = computed(() =>
  canTab('ai') ||
  canTab('smtp') ||
  canTab('mcp') ||
  canTab('runner') ||
  canTab('login') ||
  canTab('data') ||
  canTab('streamParser')
)

const resolveTopTab = (raw) => {
  const key = (raw || '').toLowerCase()
  const mapped = TOP_TAB_ALIASES[key] || key
  if (mapped === 'notify' && canTab('smtp')) return 'notify'
  if (mapped === 'ai' && canTab('ai')) return 'ai'
  if (mapped === 'mcp' && canTab('mcp')) return 'mcp'
  if (mapped === 'runner' && canTab('runner')) return 'runner'
  if (mapped === 'login' && canTab('login')) return 'login'
  if (mapped === 'data' && canTab('data')) return 'data'
  if (mapped === 'stream-parser' && canTab('streamParser')) return 'stream-parser'
  if (canTab('ai')) return 'ai'
  if (canTab('smtp')) return 'notify'
  if (canTab('mcp')) return 'mcp'
  if (canTab('runner')) return 'runner'
  if (canTab('login')) return 'login'
  if (canTab('data')) return 'data'
  if (canTab('streamParser')) return 'stream-parser'
  return 'ai'
}

const redirectLegacyProjectSettings = () => {
  const tab = String(route.query.tab || '').toLowerCase()
  const sub = String(route.query.sub || '').toLowerCase()
  // 旧：「平台配置 → 邮件与通知 → 项目通知渠道」
  if (
    sub === 'channels' ||
    tab === 'notification' ||
    tab === 'notification-config'
  ) {
    router.replace({ path: '/project-settings', query: { tab: 'notify' } })
    return true
  }
  // 旧：平台 AI 下执行与自愈
  if (sub === 'execution' || tab === 'execution') {
    router.replace({ path: '/project-settings', query: { tab: 'execution' } })
    return true
  }
  return false
}

const applyRouteTab = () => {
  if (redirectLegacyProjectSettings()) return
  activeTab.value = resolveTopTab(route.query.tab)
}

watch(() => [route.query.tab, route.query.sub], applyRouteTab, { immediate: true })

const onTabChange = (name) => {
  router.replace({ path: '/platform-config', query: { tab: name } })
}
</script>
