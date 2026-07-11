<template>
  <div class="ui-run-ai-act-tip">
    <button type="button" class="ui-run-ai-act-tip__head" @click="expanded = !expanded">
      <el-icon class="ui-run-ai-act-tip__icon"><WarningFilled /></el-icon>
      <span class="ui-run-ai-act-tip__title">{{ title }}</span>
      <el-icon class="ui-run-ai-act-tip__arrow" :class="{ 'is-expanded': expanded }">
        <ArrowDown />
      </el-icon>
    </button>
    <p v-show="expanded" class="ui-run-ai-act-tip__body">{{ description }}</p>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ArrowDown, WarningFilled } from '@element-plus/icons-vue'

defineProps({
  title: {
    type: String,
    default: '项目未开启 AI Act 总开关',
  },
  description: {
    type: String,
    default: '请在 AI 测试 → AI 模型配置 → 执行与自愈 中开启「AI Act 总开关」后，方可在此选择是否在自愈仍失败时启用 AI 兜底。',
  },
})

const expanded = ref(false)
</script>

<style scoped lang="scss">
.ui-run-ai-act-tip {
  width: 100%;
  border: 1px solid var(--el-color-warning-light-5);
  border-radius: 6px;
  background: var(--el-color-warning-light-9);
  overflow: hidden;
}

.ui-run-ai-act-tip__head {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 12px;
  border: none;
  background: transparent;
  cursor: pointer;
  text-align: left;
  font: inherit;
  color: var(--el-color-warning-dark-2);
}

.ui-run-ai-act-tip__icon {
  flex-shrink: 0;
  font-size: 16px;
}

.ui-run-ai-act-tip__title {
  flex: 1;
  font-size: 13px;
  font-weight: 500;
}

.ui-run-ai-act-tip__arrow {
  flex-shrink: 0;
  transition: transform 0.2s ease;

  &.is-expanded {
    transform: rotate(180deg);
  }
}

.ui-run-ai-act-tip__body {
  margin: 0;
  padding: 0 12px 10px 36px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--el-text-color-regular);
}
</style>
