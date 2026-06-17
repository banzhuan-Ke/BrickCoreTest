<template>
  <PageCard>
    <template #title>
      <div class="hub-head">
        <div>
          <b>智能浏览器</b>
          <span class="hub-sub">browser-use 自然语言驱动浏览器 · 用例库 · 执行 · 报告</span>
        </div>
        <el-menu mode="horizontal" :default-active="activePath" router class="hub-menu" :ellipsis="false">
          <el-menu-item index="/browser-lab/cases">用例库</el-menu-item>
          <el-menu-item index="/browser-lab/run">执行任务</el-menu-item>
          <el-menu-item index="/browser-lab/records">执行记录</el-menu-item>
        </el-menu>
      </div>
    </template>
    <template #main>
      <router-view />
    </template>
  </PageCard>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import PageCard from '@/components/PageCard.vue'

const route = useRoute()
const activePath = computed(() => {
  if (route.path.startsWith('/browser-lab/cases')) return '/browser-lab/cases'
  if (route.path.startsWith('/browser-lab/records')) return '/browser-lab/records'
  return '/browser-lab/run'
})
</script>

<style scoped>
.hub-head {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.hub-sub {
  display: block;
  font-size: 12px;
  font-weight: normal;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}
.hub-menu {
  border-bottom: none;
  background: transparent;
}
.hub-menu :deep(.el-menu-item) {
  height: 36px;
  line-height: 36px;
  padding: 0 16px;
}
</style>
