<template>
  <div class="bl-exec-options">
    <el-form-item label="最大步数">
      <el-slider v-model="form.max_steps" :min="5" :max="50" show-input />
      <div class="field-hint">{{ tips.maxSteps }}</div>
    </el-form-item>

    <el-form-item label="执行选项">
      <div class="option-checks">
        <el-checkbox v-model="form.use_vision">Vision 截图理解</el-checkbox>
        <el-checkbox v-model="form.generate_gif">生成回放 GIF</el-checkbox>
        <el-checkbox v-model="form.enable_browser_restart">CDP 异常自动续跑</el-checkbox>
      </div>
    </el-form-item>

    <el-form-item label="重复上限">
      <el-input-number v-model="form.max_repeat_steps" :min="2" :max="8" />
      <div class="field-hint">{{ tips.maxRepeat }}</div>
    </el-form-item>

    <el-form-item v-if="form.enable_browser_restart" label="续跑次数">
      <el-input-number v-model="form.max_browser_restarts" :min="1" :max="5" />
      <div class="field-hint">{{ tips.restart }}</div>
    </el-form-item>

    <el-alert type="info" :closable="false" show-icon class="option-tips-alert">
      <template #title>配置说明</template>
      <ul class="tips-list">
        <li v-for="(line, i) in tipsList" :key="i">{{ line }}</li>
      </ul>
    </el-alert>
  </div>
</template>

<script setup>
import { BROWSER_LAB_EXEC_TIPS } from './browserLabExecOptions.js'

defineProps({
  form: { type: Object, required: true }
})

const tips = BROWSER_LAB_EXEC_TIPS
const tipsList = tips.summary
</script>

<style scoped>
.option-checks {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
}
.field-hint {
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}
.option-tips-alert {
  margin-bottom: 8px;
}
.tips-list {
  margin: 4px 0 0;
  padding-left: 18px;
  font-size: 12px;
  line-height: 1.65;
  color: var(--el-text-color-regular);
}
</style>
