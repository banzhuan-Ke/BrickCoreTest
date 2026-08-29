<template>
  <el-dialog
    :model-value="modelValue"
    title="定位助手"
    width="760px"
    destroy-on-close
    append-to-body
    @update:model-value="emit('update:modelValue', $event)"
    @closed="resetForm"
  >
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="assist-tip"
      title="有调试浏览器时优先用「拾取」。本工具适合粘贴 DevTools 元素信息后生成定位。"
    />

    <el-collapse v-model="helpOpen" class="assist-help">
      <el-collapse-item title="怎么从 DevTools 粘贴？iframe 内按钮怎么写？" name="help">
        <ol class="help-list">
          <li>Chrome / Edge 打开页面 → <kbd>F12</kbd> → <strong>Elements / 元素</strong></li>
          <li>点左上角「选择元素」图标，点中目标按钮；或在树里右键节点 → <strong>Copy → Copy outerHTML</strong></li>
          <li>粘贴到下方「元素信息」。普通页面粘贴目标元素即可</li>
          <li>
            <strong>iframe 内元素</strong>：不必一次框选整段 DOM。可<strong>分别</strong>复制各层
            <code>&lt;iframe&gt;</code> 与目标按钮的 outerHTML，再<strong>按顺序粘贴到同一个输入框</strong>
            （外层 iframe → 内层 iframe → 按钮）。助手会拼成
            <code>iframe[src*="…"]||#id</code>
          </li>
          <li>两层 iframe（如业务壳 + 编辑器）时，两层 iframe 都要贴；只贴一层会提示可能缺内层</li>
        </ol>
        <p class="help-note">
          语法参考：CSS <code>#id</code>、语义 <code>get_by_text=下划线</code>、iframe
          <code>iframe||#yozo_WP_underline</code>。含 token 的完整 URL 不必整段粘贴，助手只会用
          <code>src*=</code> 截取路径片段。
        </p>
      </el-collapse-item>
    </el-collapse>

    <el-form label-position="top" class="assist-form">
      <el-form-item label="元素信息">
        <el-input
          v-model="rawElement"
          type="textarea"
          :rows="8"
          placeholder="可分开粘贴：先 iframe（多层则从上到下），再贴目标元素 outerHTML"
        />
      </el-form-item>
      <el-form-item label="意图（可选）">
        <el-input
          v-model="intent"
          placeholder="例如：点设置；取第 2 个同名；只要 title"
          clearable
        />
      </el-form-item>
      <el-form-item>
        <el-checkbox v-model="aiEnabled">AI 增强（无配置时自动降级为规则）</el-checkbox>
      </el-form-item>
      <el-button type="primary" :loading="loading" @click="generate">生成候选</el-button>
    </el-form>

    <div v-if="warnings.length" class="assist-warnings">
      <el-alert
        v-for="(w, i) in warnings"
        :key="i"
        type="warning"
        :closable="false"
        :title="w"
        show-icon
        class="assist-warn-item"
      />
    </div>

    <div v-if="candidates.length" class="assist-result">
      <div class="assist-result-head">
        候选（建议下标 {{ suggestedIndex }}）
        <el-checkbox v-model="applyAllBackups" style="margin-left: 12px">采用时写入全部备用</el-checkbox>
      </div>
      <el-radio-group v-model="selectedIdx" class="assist-radio-group">
        <div v-for="(c, idx) in candidates" :key="idx" class="assist-cand">
          <el-radio :value="idx">
            <code>{{ c.locator }}</code>
            <el-tag size="small" :type="c.source === 'ai' ? 'warning' : 'info'">{{ c.source }}</el-tag>
            <el-tag size="small" type="success" effect="plain">{{ c.confidence }}</el-tag>
            <span class="assist-reason">{{ c.reason }}</span>
          </el-radio>
        </div>
      </el-radio-group>
    </div>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-tooltip
        :disabled="canVerify"
        content="需已打开并就绪的交互调试会话"
        placement="top"
      >
        <span>
          <el-button :disabled="!canVerify || selectedIdx < 0" :loading="verifying" @click="onVerify">
            验证定位器
          </el-button>
        </span>
      </el-tooltip>
      <el-button type="primary" :disabled="selectedIdx < 0" @click="onApply">采用</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { locatorAssistApi } from '@/api/modules/ui'
import { ProjectStore } from '@/stores/module/ProjectStore.js'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  stepMethod: { type: String, default: '' },
  canVerify: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue', 'apply', 'verify'])

const proStore = ProjectStore()
const rawElement = ref('')
const intent = ref('')
const aiEnabled = ref(true)
const loading = ref(false)
const verifying = ref(false)
const candidates = ref([])
const warnings = ref([])
const suggestedIndex = ref(1)
const selectedIdx = ref(-1)
const applyAllBackups = ref(true)
const helpOpen = ref([])

function resetForm() {
  rawElement.value = ''
  intent.value = ''
  aiEnabled.value = true
  loading.value = false
  verifying.value = false
  candidates.value = []
  warnings.value = []
  suggestedIndex.value = 1
  selectedIdx.value = -1
  applyAllBackups.value = true
  helpOpen.value = []
}

watch(
  () => props.modelValue,
  (open) => {
    if (open) {
      // 每次打开都从空白开始，避免跨步骤串内容
      resetForm()
    }
  },
)

async function generate() {
  if (!rawElement.value.trim()) {
    ElMessage.warning('请先粘贴元素信息')
    return
  }
  if (!proStore.projectInfo?.id) {
    ElMessage.warning('请先选择项目')
    return
  }
  loading.value = true
  try {
    const res = await locatorAssistApi.suggest({
      project_id: proStore.projectInfo.id,
      raw_element: rawElement.value,
      intent: intent.value,
      ai_enabled: aiEnabled.value,
      step_method: props.stepMethod || '',
    })
    const data = res.data?.data || res.data || {}
    candidates.value = data.candidates || []
    warnings.value = data.warnings || []
    suggestedIndex.value = data.suggested_index || 1
    selectedIdx.value = candidates.value.length ? 0 : -1
    if (!candidates.value.length) {
      ElMessage.warning('未生成候选，请换更完整的元素信息或使用拾取')
    } else {
      ElMessage.success(`已生成 ${candidates.value.length} 条候选`)
    }
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.data?.detail || e?.message || '生成失败')
  } finally {
    loading.value = false
  }
}

function onApply() {
  const picked = candidates.value[selectedIdx.value]
  if (!picked) return
  const ordered = applyAllBackups.value
    ? [
        picked,
        ...candidates.value.filter((_, i) => i !== selectedIdx.value),
      ]
    : [picked]
  emit('apply', {
    locator: picked.locator,
    index: picked.index || suggestedIndex.value || 1,
    candidates: ordered,
    applyAll: applyAllBackups.value,
  })
  emit('update:modelValue', false)
}

async function onVerify() {
  const picked = candidates.value[selectedIdx.value]
  if (!picked || !props.canVerify) return
  verifying.value = true
  try {
    await new Promise((resolve) => {
      emit('verify', {
        locator: picked.locator,
        index: picked.index || suggestedIndex.value || 1,
        __done: resolve,
      })
      setTimeout(resolve, 90_000)
    })
  } finally {
    verifying.value = false
  }
}
</script>

<style scoped>
.assist-tip {
  margin-bottom: 10px;
}
.assist-help {
  margin-bottom: 10px;
  border: none;
}
.assist-help :deep(.el-collapse-item__header) {
  font-size: 13px;
  color: var(--el-color-primary);
  height: 36px;
  line-height: 36px;
}
.assist-help :deep(.el-collapse-item__wrap) {
  border-bottom: none;
}
.help-list {
  margin: 0;
  padding-left: 18px;
  font-size: 12px;
  line-height: 1.7;
  color: var(--el-text-color-regular);
}
.help-list kbd {
  padding: 0 4px;
  border: 1px solid var(--el-border-color);
  border-radius: 3px;
  font-size: 11px;
  background: var(--el-fill-color-light);
}
.help-note {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.6;
}
.assist-form {
  margin-top: 4px;
}
.assist-warnings {
  margin-top: 12px;
}
.assist-warn-item {
  margin-bottom: 6px;
}
.assist-result {
  margin-top: 16px;
}
.assist-result-head {
  display: flex;
  align-items: center;
  margin-bottom: 8px;
  font-weight: 600;
}
.assist-radio-group {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 8px;
  width: 100%;
}
.assist-cand :deep(.el-radio) {
  height: auto;
  align-items: flex-start;
  white-space: normal;
  width: 100%;
}
.assist-cand code {
  display: inline-block;
  margin-right: 6px;
  font-size: 12px;
  word-break: break-all;
}
.assist-reason {
  display: block;
  margin-top: 2px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
</style>
