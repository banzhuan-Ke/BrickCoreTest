<template>
  <PageCard>
    <template #title>
      <b>迭代资料库</b>
    </template>
    <template #main>
      <div class="ce-knowledge-placeholder">
        <el-alert
          type="info"
          :closable="false"
          show-icon
          title="暂未开放迭代资料库"
          description="迭代资料库本期暂不开放。需求测试、功能用例库、Embedding 配置等可正常使用。"
        />
      </div>
    </template>
  </PageCard>
</template>

<script setup>
import PageCard from '@/components/PageCard.vue'
</script>

<style scoped>
.ce-knowledge-placeholder {
  max-width: 720px;
  padding: 8px 0;
}
</style>
