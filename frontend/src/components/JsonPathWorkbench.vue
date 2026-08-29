<template>
  <div class="jp-layout" :class="{ compact }">
    <div class="jp-pane jp-pane-json">
      <div class="jp-pane-head">
        <span>JSON</span>
        <div class="jp-pane-actions">
          <el-button v-if="sampleJson.trim()" size="small" text type="primary" @click="fillSample">
            填入接口示例
          </el-button>
          <el-button size="small" text type="primary" @click="formatJson">格式化</el-button>
        </div>
      </div>
      <el-input
        :model-value="jsonText"
        type="textarea"
        :rows="compact ? 4 : 6"
        class="jp-json-input"
        placeholder="粘贴接口响应 JSON"
        @update:model-value="emit('update:jsonText', $event)"
      />
      <div class="jp-tree-wrap">
        <VueJsonPretty
          v-if="parsed.ok"
          :data="parsed.value"
          root-path="$"
          :deep="4"
          :show-line="true"
          :show-line-number="true"
          :show-icon="true"
          selectable-type="single"
          :select-on-click-node="true"
          :highlight-selected-node="true"
          @node-click="onNodeClick"
          @selected-change="onSelectedChange"
        >
          <template #renderNodeActions="{ node }">
            <button type="button" class="jp-extract-btn" @click.stop="extractNode(node)">
              提取 JSONPath
            </button>
          </template>
        </VueJsonPretty>
        <el-alert v-else type="warning" :closable="false" show-icon :title="parsed.error" />
      </div>
    </div>

    <div class="jp-pane jp-pane-path">
      <div class="jp-pane-head"><span>JSONPath</span></div>
      <p class="jp-hint">可以在左侧悬停于一个字段上点击「提取 JSONPath」来快速填写</p>
      <el-input
        :model-value="path"
        placeholder="如: $.data.token"
        @update:model-value="emit('update:path', $event)"
        @keydown.enter.prevent="emit('enter')"
      >
        <template #suffix>
          <el-button
            link
            type="primary"
            size="small"
            :disabled="!copyablePath"
            @click.stop="copyPath"
          >
            复制
          </el-button>
        </template>
      </el-input>
      <div class="jp-unpack">
        <span class="jp-unpack-title">
          数组解包
          <el-tooltip placement="top" :show-after="200">
            <template #content>
              <div class="jp-help">
                <p>点选数组里的字段时决定写成 [0] 还是 [*]：</p>
                <p>· 关闭：<code>$.data.list[0].id</code> → 只取第一条（如 13）</p>
                <p>· 开启：<code>$.data.list[*].id</code> → 一次取全部项（如 [13, 5]）</p>
                <p>路径没有数组下标时（如 <code>$.data.list</code>），开关不影响结果。</p>
              </div>
            </template>
            <el-icon class="jp-help-icon"><QuestionFilled /></el-icon>
          </el-tooltip>
        </span>
        <el-switch v-model="unpackArrays" />
      </div>
      <div class="jp-result-head">
        <span>提取结果</span>
      </div>
      <pre class="jp-result" :class="{ empty: result.empty }">{{ result.text }}</pre>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { QuestionFilled } from '@element-plus/icons-vue'
import VueJsonPretty from 'vue-json-pretty'
import 'vue-json-pretty/lib/styles.css'
import { copyToClipboard } from '@/utils/clipboard.js'
import { formatJsonText } from '@/utils/jsonFormat.js'
import {
  applyArrayUnpack,
  evalJsonPath,
  formatJsonPathResult,
  parseJsonSample,
  prettyPathToJsonPath,
} from '@/utils/jsonPath.js'

const props = defineProps({
  jsonText: { type: String, default: '' },
  path: { type: String, default: '' },
  sampleJson: { type: String, default: '' },
  compact: { type: Boolean, default: false },
})

const emit = defineEmits(['update:jsonText', 'update:path', 'enter', 'preview'])

const unpackArrays = ref(/\[\*\]/.test(props.path || ''))

const parsed = computed(() => parseJsonSample(props.jsonText))

const effectivePath = computed(() => (
  unpackArrays.value ? applyArrayUnpack(props.path) : props.path
))

const result = computed(() => {
  if (!parsed.value.ok) {
    return { text: parsed.value.error || 'JSON 无法解析', empty: true, live: false }
  }
  const raw = String(props.path || '').trim()
  if (!raw) return { text: '请填写 JSONPath', empty: true, live: false }
  const evaluated = evalJsonPath(parsed.value.value, effectivePath.value)
  if (!evaluated.ok) {
    return { text: evaluated.error || 'JSONPath 无效', empty: true, live: false }
  }
  const formatted = formatJsonPathResult(evaluated.matches)
  return { ...formatted, live: true }
})

const copyablePath = computed(() => String(effectivePath.value || '').trim())

function syncUnpackedPath() {
  if (!unpackArrays.value) return
  const next = applyArrayUnpack(props.path)
  if (next !== props.path) emit('update:path', next)
}

watch(unpackArrays, (on) => {
  if (on) syncUnpackedPath()
})

watch(
  () => props.path,
  (p) => {
    if (/\[\*\]/.test(p || '')) unpackArrays.value = true
    else syncUnpackedPath()
  },
)

watch(result, (val) => emit('preview', val), { immediate: true })

function fillSample() {
  if (!props.sampleJson.trim()) return
  emit('update:jsonText', props.sampleJson)
}

function formatJson() {
  const formatted = formatJsonText(props.jsonText)
  if (!formatted.ok) {
    ElMessage.error(formatted.error)
    return
  }
  emit('update:jsonText', formatted.text)
}

function pathFromEvent(payload) {
  if (payload == null || payload === '') return ''
  if (typeof payload === 'string') return payload
  if (typeof payload === 'object' && payload.path != null) return String(payload.path)
  return ''
}

function extractNode(payload) {
  const raw = pathFromEvent(payload)
  if (!raw) return
  emit('update:path', prettyPathToJsonPath(raw, { unpackArrays: unpackArrays.value }))
}

function onNodeClick(node) {
  extractNode(node)
}

function onSelectedChange(newVal) {
  extractNode(newVal)
}

async function copyPath() {
  const next = copyablePath.value
  if (!next) return
  const ok = await copyToClipboard(next)
  if (ok) ElMessage.success('已复制 JSONPath')
  else ElMessage.error('复制失败')
}
</script>

<style scoped>
.jp-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(260px, 0.85fr);
  gap: 16px;
  min-height: 520px;
}
.jp-layout.compact {
  min-height: 420px;
}
.jp-pane {
  min-width: 0;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 12px;
  background: var(--el-fill-color-blank);
}
.jp-pane-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  font-weight: 600;
}
.jp-pane-actions {
  display: flex;
  gap: 4px;
}
.jp-json-input :deep(textarea) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
}
.jp-tree-wrap {
  flex: 1;
  min-height: 220px;
  margin-top: 8px;
  overflow: auto;
  border: 1px solid var(--el-border-color-extra-light);
  border-radius: 6px;
  padding: 8px;
  background: var(--el-fill-color-lighter);
}
.jp-hint {
  margin: 0 0 10px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}
.jp-unpack {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin: 12px 0;
  font-size: 13px;
}
.jp-unpack-title {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.jp-help-icon {
  color: var(--el-text-color-secondary);
  cursor: help;
  font-size: 14px;
}
.jp-result-head {
  margin-bottom: 6px;
  font-size: 13px;
}
.jp-result {
  flex: 1;
  margin: 0;
  min-height: 140px;
  padding: 10px;
  border-radius: 6px;
  background: var(--el-fill-color-lighter);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-all;
}
.jp-result.empty {
  color: var(--el-text-color-secondary);
}
.jp-extract-btn {
  margin-left: 8px;
  padding: 0 6px;
  border: none;
  border-radius: 4px;
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  font-size: 12px;
  cursor: pointer;
  opacity: 0.85;
}
:deep(.vjs-tree-node:hover .jp-extract-btn),
.jp-extract-btn:hover,
.jp-extract-btn:focus {
  opacity: 1;
}
@media (max-width: 800px) {
  .jp-layout {
    grid-template-columns: 1fr;
    min-height: 0;
  }
}
</style>
