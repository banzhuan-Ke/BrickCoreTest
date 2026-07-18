<template>
  <PageCard class="knowledge-layout">
    <template #title>
      <b>迭代资料库</b>
    </template>
    <template #main>
      <el-empty description="迭代资料库开发测试中，后续放出">
        <p class="hint">请先使用 AI 测试、Web 自动化等已开放功能。进度见版本更新记录。</p>
        <el-button type="primary" @click="$router.push('/ai-testing')">前往 AI 测试</el-button>
      </el-empty>
    </template>
  </PageCard>
</template>

<script setup>
import PageCard from '@/components/PageCard.vue'
</script>

<style scoped>
.hint {
  margin: 8px 0 16px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.5;
  max-width: 420px;
}
</style>
