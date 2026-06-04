<template>
  <PageCard>
    <template #title>
      <div style="font-size: 18px; font-weight: bold;">🚀 性能测试</div>
    </template>
    <template #main>
      <el-empty description="性能测试模块开发中，敬请期待...">
        <el-icon :size="60" color="#67C23A"><TrendCharts /></el-icon>
      </el-empty>
    </template>
  </PageCard>
</template>

<script setup>
import PageCard from "@/components/PageCard.vue"
</script>
