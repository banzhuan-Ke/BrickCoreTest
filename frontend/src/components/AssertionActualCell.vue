<template>
  <div class="assertion-actual-cell">
    <template v-if="isLong">
      <div class="actual-summary" :class="{ 'is-fail': !row.passed }">
        <span v-if="summaryHint" class="hint-text">{{ summaryHint }}</span>
        <span v-else class="preview-text">{{ preview }}</span>
      </div>
      <el-button link type="primary" size="small" class="view-btn" @click="dialogVisible = true">
        查看全文
      </el-button>
      <el-button
        v-if="canLocateInResponse"
        link
        type="warning"
        size="small"
        class="view-btn"
        @click="handleLocateInResponse"
      >
        在响应中定位
      </el-button>
    </template>
    <template v-else>
      <span class="preview-text" :title="fullText">{{ preview }}</span>
      <el-button
        v-if="canLocateInResponse"
        link
        type="warning"
        size="small"
        class="view-btn"
        @click="handleLocateInResponse"
      >
        在响应中定位
      </el-button>
    </template>

    <el-dialog
      v-model="dialogVisible"
      title="断言实际值"
      width="720px"
      destroy-on-close
      append-to-body
      class="assertion-actual-dialog"
    >
      <div v-if="row.expected != null && row.expected !== ''" class="dialog-meta">
        <span class="meta-label">期望值</span>
        <code>{{ String(row.expected) }}</code>
        <span v-if="matchIndex >= 0" class="meta-tag success">在响应中找到（偏移 {{ matchIndex }}）</span>
        <span v-else-if="isContainsLike" class="meta-tag fail">在响应中未找到</span>
      </div>
      <div class="dialog-meta">
        <span class="meta-label">全文</span>
        <span class="meta-size">{{ sizeLabel }}</span>
        <CopyTextButton :text="fullText" />
        <el-button
          v-if="locateInResponse && expectedText"
          link
          type="warning"
          size="small"
          @click="handleLocateInResponse"
        >
          在响应 Body 中定位
        </el-button>
      </div>
      <CopyablePre :text="fullText" max-height="420px" :wrap="true" :show-toolbar="false" />
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import CopyTextButton from '@/components/CopyTextButton.vue'
import CopyablePre from '@/components/CopyablePre.vue'
import { useAssertionResponseLocate } from '@/composables/assertionResponseLocate.js'
import {
  assertionActualToText,
  findExpectedIndex,
  formatByteSize,
  getAssertionActualPreview,
  getContainsFailHint,
  isLongAssertionActual,
} from '@/utils/assertionDisplay.js'

const props = defineProps({
  row: {
    type: Object,
    required: true,
  },
})

const dialogVisible = ref(false)
const locateInResponse = useAssertionResponseLocate()

const expectedText = computed(() => {
  const val = props.row?.expected
  if (val === null || val === undefined || val === '') return ''
  return String(val)
})

const fullText = computed(() => assertionActualToText(props.row?.actual))
const isLong = computed(() => isLongAssertionActual(props.row?.actual, props.row?.type))
const preview = computed(() => getAssertionActualPreview(props.row?.actual))
const sizeLabel = computed(() => formatByteSize(fullText.value.length))

const isContainsLike = computed(() => {
  const t = props.row?.type
  const op = props.row?.operator
  return t === 'contains' || t === 'not_contains' || op === 'contains' || op === 'not_contains'
})

const summaryHint = computed(() => {
  if (!props.row.passed && isContainsLike.value) {
    return getContainsFailHint(props.row)
  }
  return ''
})

const matchIndex = computed(() => findExpectedIndex(fullText.value, props.row?.expected))

const canLocateInResponse = computed(() => {
  if (!locateInResponse || props.row?.passed !== false) return false
  return Boolean(expectedText.value)
})

function handleLocateInResponse() {
  const term = expectedText.value
  if (!term || !locateInResponse) return
  const ok = locateInResponse(term)
  if (ok) {
    ElMessage.success('已跳转到响应 Body 并高亮期望值')
    return
  }
  ElMessage.warning('暂无响应 Body 可定位')
}
</script>

<style scoped lang="scss">
.assertion-actual-cell {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  max-width: 100%;
}

.actual-summary {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--el-text-color-regular);

  &.is-fail .hint-text {
    color: var(--el-color-danger);
  }
}

.preview-text {
  display: inline-block;
  max-width: 100%;
  font-size: 12px;
  word-break: break-all;
  line-height: 1.4;
}

.hint-text {
  word-break: break-all;
}

.view-btn {
  flex-shrink: 0;
  padding: 0;
  height: auto;
}

.dialog-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
  font-size: 13px;

  code {
    padding: 2px 6px;
    background: var(--el-fill-color-light);
    border-radius: 4px;
    font-size: 12px;
  }
}

.meta-label {
  color: var(--el-text-color-secondary);
}

.meta-size {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.meta-tag {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 4px;

  &.success {
    background: var(--el-color-success-light-9);
    color: var(--el-color-success);
  }

  &.fail {
    background: var(--el-color-danger-light-9);
    color: var(--el-color-danger);
  }
}
</style>
