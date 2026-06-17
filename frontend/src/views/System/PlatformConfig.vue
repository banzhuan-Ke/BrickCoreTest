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
        title="统一配置入口"
        description="聚合 AI 模型、邮件 SMTP、项目通知渠道、MCP Server、执行器发布与登录页等品牌配置。各 Tab 权限与原先独立菜单一致。"
        style="margin-bottom: 16px;"
      />
      <el-tabs v-model="activeTab" type="border-card" @tab-change="onTabChange">
        <el-tab-pane v-if="canTab('ai')" label="AI 模型" name="ai" lazy>
          <AiConfig embedded />
        </el-tab-pane>
        <el-tab-pane v-if="canTab('notify')" label="邮件与通知" name="notify" lazy>
          <el-tabs v-model="notifySubTab" type="card" class="notify-sub-tabs">
            <el-tab-pane v-if="canTab('smtp')" label="SMTP 发信" name="smtp" lazy>
              <SmtpConfig embedded />
            </el-tab-pane>
            <el-tab-pane v-if="canTab('notification')" label="项目通知渠道" name="channels" lazy>
              <NotificationConfig embedded />
            </el-tab-pane>
          </el-tabs>
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
import NotificationConfig from '@/views/Project/NotificationConfig.vue'

const TAB_PERMISSIONS = {
  ai: 'ai_config:view',
  smtp: 'smtp_config:view',
  notification: 'notification_config:view',
  mcp: 'mcp_config:view',
  runner: 'device:edit',
  login: 'login_page_config:view',
  data: 'platform_settings:view',
}

const TOP_TAB_ALIASES = {
  'ai-config': 'ai',
  smtp: 'notify',
  'smtp-config': 'notify',
  notification: 'notify',
  'notification-config': 'notify',
  mcp: 'mcp',
  'mcp-config': 'mcp',
  runner: 'runner',
  'runner-release-config': 'runner',
  login: 'login',
  'login-page-config': 'login',
  data: 'data',
  'data-retention': 'data',
  'platform-settings': 'data',
}

const route = useRoute()
const router = useRouter()
const uStore = UserStore()

const activeTab = ref('ai')
const notifySubTab = ref('smtp')

const canTab = (key) => {
  const perm = TAB_PERMISSIONS[key]
  return perm ? uStore.hasPermission(perm) : false
}

const hasAnyTab = computed(() =>
  canTab('ai') ||
  canTab('smtp') ||
  canTab('notification') ||
  canTab('mcp') ||
  canTab('runner') ||
  canTab('login') ||
  canTab('data')
)

const resolveTopTab = (raw) => {
  const key = (raw || '').toLowerCase()
  const mapped = TOP_TAB_ALIASES[key] || key
  if (mapped === 'notify' && (canTab('smtp') || canTab('notification'))) return 'notify'
  if (mapped === 'ai' && canTab('ai')) return 'ai'
  if (mapped === 'mcp' && canTab('mcp')) return 'mcp'
  if (mapped === 'runner' && canTab('runner')) return 'runner'
  if (mapped === 'login' && canTab('login')) return 'login'
  if (mapped === 'data' && canTab('data')) return 'data'
  if (canTab('ai')) return 'ai'
  if (canTab('smtp') || canTab('notification')) return 'notify'
  if (canTab('mcp')) return 'mcp'
  if (canTab('runner')) return 'runner'
  if (canTab('login')) return 'login'
  if (canTab('data')) return 'data'
  return 'ai'
}

const applyRouteTab = () => {
  const tab = route.query.tab
  const sub = route.query.sub
  activeTab.value = resolveTopTab(tab)
  if (activeTab.value === 'notify') {
    if (sub === 'channels' && canTab('notification')) {
      notifySubTab.value = 'channels'
    } else if (canTab('smtp')) {
      notifySubTab.value = 'smtp'
    } else if (canTab('notification')) {
      notifySubTab.value = 'channels'
    }
  }
}

watch(() => route.query.tab, applyRouteTab, { immediate: true })

const onTabChange = (name) => {
  const query = { tab: name }
  if (name === 'notify') {
    query.sub = notifySubTab.value
  }
  router.replace({ path: '/platform-config', query })
}

watch(notifySubTab, (sub) => {
  if (activeTab.value === 'notify') {
    router.replace({ path: '/platform-config', query: { tab: 'notify', sub } })
  }
})
</script>

<style scoped>
.notify-sub-tabs {
  margin-top: 4px;
}
.notify-sub-tabs :deep(.el-tabs__header) {
  margin-bottom: 12px;
}
</style>
