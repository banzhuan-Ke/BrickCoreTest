<template>
  <el-alert
    v-if="enabled"
    type="success"
    :closable="false"
    show-icon
    class="ui-run-auth-hint"
    title="当前环境已启用 Web 启动登录态注入"
    description="打开浏览器时会注入 Cookie / Storage / storage_state；用例只需打开业务 URL。不会自动跳登录后地址；会话过期请重新导出或跑登录步骤片段。"
  />
</template>

<script setup>
import { computed } from 'vue'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { envHasUiAuthInject } from '@/utils/caseDescription.js'

const props = defineProps({
  envId: {
    type: [String, Number],
    default: '',
  },
})

const proStore = ProjectStore()

const enabled = computed(() => {
  const id = props.envId
  if (id == null || id === '') return false
  const env = (proStore.envList || []).find((e) => String(e.id) === String(id))
  return envHasUiAuthInject(env?.global_vars)
})
</script>

<style scoped lang="scss">
.ui-run-auth-hint {
  margin: 0 0 8px;
  width: 100%;
}
</style>
