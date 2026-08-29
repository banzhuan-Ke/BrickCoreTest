<template>
  <span class="case-stability-badges">
    <el-tag v-if="quarantine" type="info" size="small" effect="plain">已隔离</el-tag>
    <el-tooltip v-if="unstable" :content="unstableTip" placement="top">
      <el-tag type="warning" size="small" effect="plain">不稳定</el-tag>
    </el-tooltip>
  </span>
</template>

<script setup>
defineProps({
  quarantine: { type: Boolean, default: false },
  unstable: { type: Boolean, default: false },
  unstableTip: {
    type: String,
    default: '窗口内时好时坏，或通过率低于项目阈值（项目设置可调）',
  },
})
</script>

<style scoped>
.case-stability-badges {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
  line-height: 1;
}
.case-stability-badges :deep(.el-tag) {
  vertical-align: middle;
  height: 20px;
  line-height: 18px;
}
</style>
