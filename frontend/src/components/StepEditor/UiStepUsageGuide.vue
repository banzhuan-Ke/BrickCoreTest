<template>
  <el-tooltip
    v-if="guide"
    placement="top"
    :show-after="150"
    popper-class="ui-step-guide-popper"
  >
    <template #content>
      <div class="guide-tip">
        <div class="guide-tip-title">{{ guide.title }}</div>
        <p v-for="(line, idx) in guide.paragraphs" :key="idx">{{ line }}</p>
        <pre v-if="guide.example" class="guide-tip-example">{{ guide.example }}</pre>
      </div>
    </template>
    <span class="guide-trigger" tabindex="0">
      <el-icon class="guide-tip-icon"><QuestionFilled /></el-icon>
      <span v-if="showLabel" class="guide-trigger-text">使用说明</span>
    </span>
  </el-tooltip>
</template>

<script setup>
import { computed } from 'vue'
import { QuestionFilled } from '@element-plus/icons-vue'
import { getStepUsageGuide } from '@/utils/uiStepMeta.js'

const props = defineProps({
  method: {
    type: String,
    default: '',
  },
  /** 是否显示「使用说明」文字（无配置参数时可看清入口） */
  showLabel: {
    type: Boolean,
    default: false,
  },
})

const guide = computed(() => getStepUsageGuide(props.method))
</script>

<style scoped lang="scss">
.guide-trigger {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  cursor: help;
  vertical-align: middle;
  outline: none;
}

.guide-tip-icon {
  font-size: 14px;
  color: var(--el-color-primary);
}

.guide-trigger-text {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>

<style lang="scss">
.ui-step-guide-popper {
  max-width: 420px;

  .guide-tip {
    font-size: 13px;
    line-height: 1.55;
  }

  .guide-tip-title {
    margin-bottom: 8px;
    font-weight: 600;
  }

  .guide-tip p {
    margin: 0 0 6px;

    &:last-of-type {
      margin-bottom: 0;
    }
  }

  .guide-tip-example {
    margin: 8px 0 0;
    padding: 8px 10px;
    font-size: 12px;
    line-height: 1.45;
    background: rgba(0, 0, 0, 0.06);
    border-radius: 6px;
    white-space: pre-wrap;
    word-break: break-word;
  }
}
</style>
