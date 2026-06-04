<template>
  <div class="response-body-viewer" :class="{ 'response-body-viewer--fill': fill }">
    <div class="response-body-viewer__toolbar">
      <el-radio-group
        v-if="formattable"
        v-model="viewMode"
        size="small"
        class="response-body-viewer__mode"
      >
        <el-radio-button label="pretty">JSON 格式</el-radio-button>
        <el-radio-button label="compact">单行</el-radio-button>
      </el-radio-group>
      <CopyTextButton v-if="displayText" :text="displayText" />
      <slot name="extra" />
    </div>
    <CopyablePre
      ref="preRef"
      :text="displayText"
      :highlight-text="highlightText"
      :max-height="maxHeight"
      :min-height="minHeight"
      :fill="fill"
      :show-toolbar="false"
    />
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import CopyablePre from '@/components/CopyablePre.vue'
import CopyTextButton from '@/components/CopyTextButton.vue'
import {
  compactResponseJson,
  formatResponseJson,
  isResponseJsonFormattable,
} from '@/views/ApiModule/utils/formatResponse.js'

const props = defineProps({
  body: { type: [String, Number, Object, Array], default: null },
  highlightText: { type: String, default: '' },
  maxHeight: { type: String, default: '480px' },
  minHeight: { type: String, default: '' },
  fill: { type: Boolean, default: false },
  defaultMode: { type: String, default: 'pretty' },
})

const preRef = ref(null)
const viewMode = ref(props.defaultMode)

const formattable = computed(() => isResponseJsonFormattable(props.body))

const displayText = computed(() => {
  if (props.body === null || props.body === undefined || props.body === '') return ''
  if (!formattable.value) {
    if (typeof props.body === 'object') {
      try {
        return JSON.stringify(props.body, null, 2)
      } catch {
        return String(props.body)
      }
    }
    return String(props.body)
  }
  return viewMode.value === 'compact'
    ? compactResponseJson(props.body)
    : formatResponseJson(props.body)
})

watch(
  () => props.body,
  () => {
    viewMode.value = props.defaultMode
  }
)

function scrollToFirstHighlight() {
  preRef.value?.scrollToFirstHighlight?.()
}

defineExpose({ scrollToFirstHighlight })
</script>

<style scoped lang="scss">
.response-body-viewer {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;

  &--fill {
    flex: 1;
    min-height: 0;
  }
}

.response-body-viewer__toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.response-body-viewer__mode {
  margin-right: 4px;
}
</style>
