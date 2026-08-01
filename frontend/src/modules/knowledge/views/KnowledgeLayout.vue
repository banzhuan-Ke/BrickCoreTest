<template>
  <PageCard class="knowledge-layout">
    <template #title>
      <div class="hub-head">
        <div class="hub-title-row">
          <b>迭代资料库</b>
          <span v-if="showHubSub" class="hub-sub">{{ hubSubText }}</span>
        </div>
        <el-menu mode="horizontal" :default-active="activePath" router class="hub-menu" :ellipsis="false">
          <el-menu-item index="/ai-knowledge/search">资料检索</el-menu-item>
          <el-menu-item index="/ai-knowledge/qa">资料问答</el-menu-item>
          <el-menu-item index="/ai-knowledge/folders">迭代文件夹</el-menu-item>
          <el-menu-item index="/ai-knowledge/templates">输出模板</el-menu-item>
          <el-menu-item index="/ai-knowledge/variables">模板变量</el-menu-item>
          <el-menu-item index="/ai-knowledge/reports">报告向导</el-menu-item>
          <el-menu-item index="/ai-knowledge/records">生成记录</el-menu-item>
          <el-menu-item index="/ai-knowledge/settings">生成配置</el-menu-item>
          <el-menu-item index="/ai-knowledge/pro-custom">定制文档</el-menu-item>
        </el-menu>
      </div>
    </template>
    <template #main>
      <router-view />
    </template>
  </PageCard>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import PageCard from '@/components/PageCard.vue'
import { knowledgeApi } from '@/api/modules/knowledge.js'

const route = useRoute()
const packEnabled = ref(false)

const activePath = computed(() => {
  if (route.path.startsWith('/ai-knowledge/pro-custom')) return '/ai-knowledge/pro-custom'
  if (route.path.startsWith('/ai-knowledge/qa')) return '/ai-knowledge/qa'
  if (route.path.startsWith('/ai-knowledge/search')) return '/ai-knowledge/search'
  if (route.path.startsWith('/ai-knowledge/records')) return '/ai-knowledge/records'
  if (route.path.startsWith('/ai-knowledge/variables')) return '/ai-knowledge/variables'
  if (route.path.startsWith('/ai-knowledge/templates')) return '/ai-knowledge/templates'
  if (route.path.startsWith('/ai-knowledge/reports')) return '/ai-knowledge/reports'
  if (route.path.startsWith('/ai-knowledge/settings')) return '/ai-knowledge/settings'
  if (route.path.startsWith('/ai-knowledge/folders')) return '/ai-knowledge/folders'
  return '/ai-knowledge/folders'
})

const showHubSub = computed(() => hubSubText.value !== '')
const hubSubText = computed(() => {
  const p = route.path
  if (p.startsWith('/ai-knowledge/qa')) return '资料问答 — 检索模式零 LLM 费用；智能模式基于资料片段生成回答'
  if (p.startsWith('/ai-knowledge/search')) return '资料检索 — 按关键词检索历史 Bug、测试计划等文档分块'
  if (p.startsWith('/ai-knowledge/folders')) return '迭代文件夹 — 按迭代组织需求、Bug、测试计划等文档'
  if (p.startsWith('/ai-knowledge/templates')) return '输出模板 — 迭代报告、质量回顾等 Word/PPT 模板'
  if (p.startsWith('/ai-knowledge/variables')) return '模板变量 — 报告生成时的占位符与默认值'
  if (p.startsWith('/ai-knowledge/reports')) return '报告向导 — 选择资料与执行记录，生成迭代测试报告'
  if (p.startsWith('/ai-knowledge/records')) return '生成记录 — 查看报告生成进度与下载'
  if (p.startsWith('/ai-knowledge/settings')) return '生成配置 — RAG、摘要、项目级设置'
  if (p.startsWith('/ai-knowledge/pro-custom')) return '定制文档 — 行业定制报告与方案（需开通）'
  return ''
})

onMounted(async () => {
  try {
    const res = await knowledgeApi.getMeta()
    packEnabled.value = !!res.data?.knowledge_pack_enabled
  } catch {
    packEnabled.value = false
  }
})
</script>

<style scoped>
.knowledge-layout :deep(.title) {
  height: auto;
  min-height: 56px;
  align-items: flex-start;
  padding: 14px 20px 10px;
}
.hub-head {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 100%;
  padding-top: 2px;
}
.hub-title-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.hub-sub {
  display: block;
  font-size: 12px;
  font-weight: normal;
  color: var(--el-text-color-secondary);
  line-height: 1.4;
}
.hub-menu {
  border-bottom: none;
  background: transparent;
  margin-top: 2px;
}
.hub-menu :deep(.el-menu-item) {
  height: 36px;
  line-height: 36px;
  padding: 0 16px;
}
</style>
