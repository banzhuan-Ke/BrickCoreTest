<template>
  <div class="copyable-pre" :class="{ 'copyable-pre--fill': fill }">
    <div v-if="showToolbar" class="copyable-pre__toolbar">
      <CopyTextButton :text="displayText" :label="copyLabel" />
      <span v-if="highlightHint" class="copyable-pre__hint copyable-pre__hint--highlight">{{ highlightHint }}</span>
      <span v-else-if="hint" class="copyable-pre__hint">{{ hint }}</span>
    </div>
    <div ref="scrollRef" class="copyable-pre__scroll" :style="scrollStyle">
      <pre
        v-if="highlightText"
        class="copyable-pre__content copyable-pre__content--wrap copyable-pre__content--highlighted"
        v-html="highlightedHtml"
      />
      <pre
        v-else
        class="copyable-pre__content"
        :class="{ 'copyable-pre__content--wrap': wrap }"
        :title="clickToCopy ? '双击复制' : undefined"
        @dblclick="clickToCopy ? handleDblClick() : undefined"
      >{{ displayText }}</pre>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import CopyTextButton from '@/components/CopyTextButton.vue'
import { copyToClipboard } from '@/utils/clipboard.js'
import { buildHighlightedHtml, countHighlightMatches } from '@/utils/assertionDisplay.js'

const props = defineProps({
  text: { type: [String, Number, Object, Array], default: '' },
  maxHeight: { type: String, default: '' },
  minHeight: { type: String, default: '' },
  wrap: { type: Boolean, default: false },
  fill: { type: Boolean, default: false },
  showToolbar: { type: Boolean, default: true },
  copyLabel: { type: String, default: '复制' },
  hint: { type: String, default: '双击内容也可复制' },
  clickToCopy: { type: Boolean, default: true },
  highlightText: { type: String, default: '' },
})

const scrollRef = ref(null)

const displayText = computed(() => {
  const value = props.text
  if (value === null || value === undefined || value === '') return ''
  if (typeof value === 'string') return value
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value, null, 2)
    } catch {
      return String(value)
    }
  }
  return String(value)
})

const highlightedHtml = computed(() =>
  buildHighlightedHtml(displayText.value, props.highlightText)
)

const highlightHint = computed(() => {
  const term = (props.highlightText || '').trim()
  if (!term) return ''
  const count = countHighlightMatches(displayText.value, term)
  if (count > 0) return `已高亮「${term.length > 20 ? `${term.slice(0, 20)}…` : term}」${count > 1 ? `（${count} 处）` : ''}`
  return `未找到「${term.length > 20 ? `${term.slice(0, 20)}…` : term}」`
})

const scrollStyle = computed(() => {
  const style = {}
  if (props.maxHeight) style.maxHeight = props.maxHeight
  if (props.minHeight) style.minHeight = props.minHeight
  if (props.fill) style.flex = '1'
  return style
})

async function handleDblClick() {
  if (!displayText.value) return
  const ok = await copyToClipboard(displayText.value)
  if (ok) ElMessage.success('已复制到剪贴板')
}

function scrollToFirstHighlight() {
  nextTick(() => {
    const mark = scrollRef.value?.querySelector('.copyable-pre__highlight')
    mark?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  })
}

watch(
  () => [props.highlightText, displayText.value],
  () => {
    if (props.highlightText) scrollToFirstHighlight()
  }
)

defineExpose({ scrollToFirstHighlight })
</script>

<style scoped lang="scss">
.copyable-pre {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 6px;

  &--fill {
    flex: 1;
    min-height: 0;
  }
}

.copyable-pre__toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.copyable-pre__hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);

  &--highlight {
    color: var(--el-color-warning);
  }
}

.copyable-pre__scroll {
  overflow: auto;
  background: var(--el-fill-color-light, #f5f7fa);
  border-radius: 4px;
  border: 1px solid var(--el-border-color-lighter, #ebeef5);
  box-sizing: border-box;
}

.copyable-pre--fill .copyable-pre__scroll {
  flex: 1;
  min-height: 0;
}

.copyable-pre__content {
  margin: 0;
  padding: 12px 16px;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.5;
  white-space: pre;
  word-break: normal;
  overflow-wrap: normal;
  width: max-content;
  min-width: 100%;
  box-sizing: border-box;
  cursor: default;

  &--wrap {
    white-space: pre-wrap;
    word-break: break-word;
    overflow-wrap: anywhere;
    width: 100%;
    min-width: 0;
  }

  &--highlighted {
    white-space: pre-wrap;
    word-break: break-word;
    overflow-wrap: anywhere;
    width: 100%;
    min-width: 0;

    :deep(.copyable-pre__highlight) {
      background: #ffe58f;
      color: inherit;
      padding: 0 2px;
      border-radius: 2px;
    }
  }
}
</style>
