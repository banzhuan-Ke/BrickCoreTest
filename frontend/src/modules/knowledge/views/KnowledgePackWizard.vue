<template>
  <div class="pack-locked">
    <el-alert type="info" show-icon :closable="false" title="定制能力未开通">
      定制测试方案 / 报告 / 质量回顾等能力需按需开通。如需使用，请联系管理员进行定制开发。
    </el-alert>
    <el-empty description="页签已预留，开通后可在此生成与下载定制文档" />
  </div>
</template>

<script setup>
</script>

<style scoped>
.pack-locked {
  padding: 8px 4px 24px;
  max-width: 720px;
}
.pack-locked :deep(.el-empty) {
  padding: 32px 0 8px;
}
</style>
