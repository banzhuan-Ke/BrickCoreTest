<template>
  <el-form-item label="已隔离用例">
    <el-checkbox v-model="model">包含已隔离用例（默认跳过）</el-checkbox>
    <div class="hint">已打「隔离」标记的用例默认不进计划/套件通过率分母</div>
  </el-form-item>
</template>

<script setup>
const model = defineModel({ type: Boolean, default: false })
</script>

<style scoped>
.hint {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.4;
}
</style>
