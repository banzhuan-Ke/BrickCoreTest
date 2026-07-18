<template>
  <PageCard>
    <template #title>
      <b>项目设置</b>
    </template>
    <template #main>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        style="margin-bottom: 16px;"
        title="本页仅为项目级配置"
        :description="projectHint"
      />
      <el-tabs v-model="activeTab" type="border-card" @tab-change="onTabChange">
        <el-tab-pane v-if="canExecution" label="自愈与 AI Act" name="heal" />
        <el-tab-pane v-if="canExecution" label="录制与调试" name="recording" />
        <el-tab-pane v-if="canExecution" label="失败分析" name="failure" />
        <el-tab-pane v-if="canExecution" label="功能用例" name="cases" />
        <el-tab-pane v-if="canNotify" label="通知渠道" name="notify" />
      </el-tabs>
      <div v-if="hasAnyTab" class="project-settings-body">
        <AiExecutionSettings
          v-if="canExecution"
          v-show="isExecTab"
          :section="execSection"
          compact-hint
          :can-edit="canExecutionEdit"
        />
        <NotificationConfig
          v-if="canNotify && activeTab === 'notify'"
          embedded
          :can-edit="canNotifyEdit"
        />
      </div>
      <el-empty v-else description="当前账号无项目设置相关权限" />
    </template>
  </PageCard>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PageCard from '@/components/PageCard.vue'
import { UserStore } from '@/stores/module/UserStore'
import { ProjectStore } from '@/stores/module/ProjectStore'
import AiExecutionSettings from '@/views/AI/AiExecutionSettings.vue'
import NotificationConfig from '@/views/Project/NotificationConfig.vue'

const route = useRoute()
const router = useRouter()
const uStore = UserStore()
const proStore = ProjectStore()

const canExecution = computed(() =>
  uStore.hasPermission('project_settings:view') || uStore.hasPermission('ai_config:view')
)
const canExecutionEdit = computed(() =>
  uStore.hasPermission('project_settings:edit') || uStore.hasPermission('ai_config:edit')
)
const canNotify = computed(() => uStore.hasPermission('notification_config:view'))
const canNotifyEdit = computed(() => uStore.hasPermission('notification_config:edit'))
const hasAnyTab = computed(() => canExecution.value || canNotify.value)

const EXEC_TABS = new Set(['heal', 'recording', 'failure', 'cases'])
const activeTab = ref('heal')
const execSection = ref('heal')
const isExecTab = computed(() => EXEC_TABS.has(activeTab.value))

watch(activeTab, (tab) => {
  if (EXEC_TABS.has(tab)) execSection.value = tab
})

const projectHint = computed(() => {
  const name = proStore.projectInfo?.name
  const base = '仅可配置当前顶栏项目；全站模型 / SMTP / 登录页等请到「系统管理 → 平台配置」。'
  let hint = name ? `当前顶栏项目：${name}。${base}` : `尚未选择项目时，各策略页无法保存。${base}`
  if (canExecution.value && !canExecutionEdit.value) {
    hint += ' 当前为只读：可查看策略，保存需「项目设置-编辑」。'
  }
  return hint
})

const resolveTab = (raw) => {
  const key = (raw || '').toLowerCase()
  if (['execution', 'exec', 'heal', 'ai-act', 'act'].includes(key) && canExecution.value) return 'heal'
  if (['recording', 'record', 'debug', 'locator'].includes(key) && canExecution.value) return 'recording'
  if (['failure', 'analyze', 'analysis'].includes(key) && canExecution.value) return 'failure'
  if (['cases', 'case', 'requirement', 'soft-range'].includes(key) && canExecution.value) return 'cases'
  if (['notify', 'notification', 'channels', 'notification-config'].includes(key) && canNotify.value) {
    return 'notify'
  }
  if (canExecution.value) return 'heal'
  if (canNotify.value) return 'notify'
  return 'heal'
}

const applyRouteTab = () => {
  activeTab.value = resolveTab(route.query.tab)
}

watch(() => route.query.tab, applyRouteTab, { immediate: true })

const onTabChange = (name) => {
  router.replace({ path: '/project-settings', query: { tab: name } })
}
</script>

<style scoped>
.project-settings-body {
  margin-top: 16px;
}
</style>
