<template>
  <span class="tool-insert-wrap">
    <el-popover
      trigger="click"
      placement="bottom-start"
      :width="460"
      popper-class="tool-insert-popover"
      @show="onPopoverShow"
    >
      <template #reference>
        <el-button
          :size="size"
          :type="type"
          :link="link"
          :icon="Tools"
          @mousedown="onReferenceMouseDown"
        >
          {{ label }}
        </el-button>
      </template>

      <div class="tool-insert-panel">
        <el-input
          v-model="searchKeyword"
          placeholder="搜索工具名称 / 说明"
          clearable
          size="small"
          prefix-icon="Search"
          class="tool-search"
        />
        <p class="tool-insert-tip">
          执行时自动计算；套件/计划内<strong>同一表达式只算一次</strong>（随机数等同次运行保持一致）。<br />
          引用变量：<code>@变量名</code>；固定值：用 <code>"..."</code> 或 <code>'...'</code> 包裹，可含 <code>|</code>、<code>=</code>、<code>@</code>，例如 <code v-pre>${{dt:md5|text="test@163.com"}}</code>。
        </p>
        <div class="tool-list">
          <template v-if="groupedTools.length">
            <div v-for="block in groupedTools" :key="block.category" class="tool-group">
              <div class="tool-group-title">{{ block.label }}</div>
              <div
                v-for="tool in block.tools"
                :key="tool.id"
                class="tool-row"
                @click="onPickTool(tool)"
              >
                <span class="tool-name">{{ tool.name }}</span>
                <span class="tool-desc">{{ tool.description }}</span>
              </div>
            </div>
          </template>
          <div v-else-if="!loading" class="tool-empty">无匹配工具</div>
          <div v-else class="tool-empty">加载中…</div>
        </div>
      </div>
    </el-popover>

    <el-dialog
      v-model="paramDialogVisible"
      :title="pickedTool ? `插入工具：${pickedTool.name}` : '插入工具'"
      width="520px"
      append-to-body
      destroy-on-close
      class="tool-insert-param-dialog"
      @closed="resetParamForm"
    >
      <template v-if="pickedTool">
        <p class="dialog-desc">{{ pickedTool.description }}</p>
        <el-alert type="info" :closable="false" show-icon class="param-tips">
          <template #title>参数写法</template>
          <ul class="tips-list">
            <li><strong>引用变量</strong>：选「引用变量」，生成 <code>@token</code></li>
            <li><strong>固定值</strong>：选「固定值」，插入时会<strong>自动加双引号</strong>，如 <code v-pre>"test@163.com"</code>、<code v-pre>"a|b=c"</code></li>
            <li>手动编写时：固定值请写 <code v-pre>${{dt:md5|text="hello|world"}}</code>；勿把固定值写成 <code>@test@163.com</code></li>
          </ul>
        </el-alert>
        <el-form label-width="100px" size="default">
          <el-form-item
            v-for="field in pickedTool.inputs"
            :key="field.key"
            :label="field.label"
            :required="field.required"
          >
            <div class="param-field">
              <el-radio-group v-model="paramModes[field.key]" size="small" class="param-mode">
                <el-radio-button value="literal">固定值</el-radio-button>
                <el-radio-button value="var">引用变量</el-radio-button>
              </el-radio-group>
              <el-select
                v-if="paramModes[field.key] === 'var'"
                v-model="paramValues[field.key]"
                placeholder="选择变量"
                filterable
                allow-create
                default-first-option
                style="width: 100%;"
              >
                <el-option v-for="v in variableOptions" :key="v" :label="v" :value="`@${v}`" />
              </el-select>
              <el-input-number
                v-else-if="field.type === 'number'"
                v-model="paramValues[field.key]"
                controls-position="right"
                style="width: 100%;"
              />
              <el-input
                v-else-if="field.type === 'textarea'"
                v-model="paramValues[field.key]"
                type="textarea"
                :rows="3"
                :placeholder="field.placeholder || ''"
              />
              <el-input
                v-else
                v-model="paramValues[field.key]"
                :placeholder="field.placeholder || ''"
              />
            </div>
          </el-form-item>
        </el-form>
        <div v-if="previewExpr" class="preview-expr">
          将插入：<code>{{ previewExpr }}</code>
        </div>
      </template>
      <template #footer>
        <el-button @click="paramDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmInsert">插入</el-button>
      </template>
    </el-dialog>
  </span>
</template>

<script setup>
import { computed, ref } from 'vue'
import { Tools } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { dataFactoryApi } from '@/api/modules/dataFactory'
import { BUILTIN_VAR_HINTS } from '@/utils/globalVars.js'
import { formatDtToolRef, insertDtToolRef } from '@/utils/dtToolInsert.js'
import { snapshotInsertTarget } from '@/utils/varInsert.js'

const props = defineProps({
  extraVars: { type: Array, default: () => [] },
  label: { type: String, default: '插入工具' },
  size: { type: String, default: 'small' },
  type: { type: String, default: 'success' },
  link: { type: Boolean, default: false },
})

const loading = ref(false)
const categories = ref([])
const tools = ref([])
const searchKeyword = ref('')
const paramDialogVisible = ref(false)
const pickedTool = ref(null)
const paramValues = ref({})
const paramModes = ref({})

const categoryLabelMap = computed(() => {
  const map = new Map()
  for (const c of categories.value) map.set(c.id, c.label)
  return map
})

const variableOptions = computed(() => {
  const set = new Set()
  for (const key of props.extraVars) {
    if (key) set.add(String(key))
  }
  for (const item of BUILTIN_VAR_HINTS) set.add(item.key)
  return [...set]
})

const filteredTools = computed(() => {
  const q = searchKeyword.value.trim().toLowerCase()
  if (!q) return tools.value
  return tools.value.filter((t) => {
    const hay = `${t.name} ${t.description} ${t.id}`.toLowerCase()
    return hay.includes(q)
  })
})

const groupedTools = computed(() => {
  const map = new Map()
  for (const tool of filteredTools.value) {
    const cat = tool.category || 'other'
    if (!map.has(cat)) map.set(cat, [])
    map.get(cat).push(tool)
  }
  return [...map.entries()].map(([category, list]) => ({
    category,
    label: categoryLabelMap.value.get(category) || category,
    tools: list,
  }))
})

const previewExpr = computed(() => {
  if (!pickedTool.value) return ''
  const payload = buildInsertPayload()
  if (!payload) return ''
  return formatDtToolRef(pickedTool.value.id, payload.params, payload.options)
})

async function loadCatalog() {
  loading.value = true
  try {
    const res = await dataFactoryApi.getInlineToolsCatalog()
    categories.value = res.data?.categories || []
    tools.value = res.data?.tools || []
  } catch {
    categories.value = []
    tools.value = []
    ElMessage.error('加载工具目录失败')
  } finally {
    loading.value = false
  }
}

function onReferenceMouseDown() {
  snapshotInsertTarget()
}

function onPopoverShow() {
  searchKeyword.value = ''
  snapshotInsertTarget()
  loadCatalog()
}

function resetParamForm() {
  pickedTool.value = null
  paramValues.value = {}
  paramModes.value = {}
}

function initParamForm(tool) {
  const values = {}
  const modes = {}
  for (const field of tool.inputs || []) {
    if (field.type === 'number') {
      values[field.key] = field.default ?? 0
    } else {
      values[field.key] = field.default ?? ''
    }
    modes[field.key] = 'literal'
  }
  paramValues.value = values
  paramModes.value = modes
}

function onPickTool(tool) {
  if (!tool.inputs?.length) {
    doInsert(tool.id, {})
    return
  }
  pickedTool.value = tool
  initParamForm(tool)
  paramDialogVisible.value = true
}

function buildInsertPayload() {
  const params = {}
  const paramModesOut = {}
  const fieldTypes = {}
  for (const field of pickedTool.value?.inputs || []) {
    const key = field.key
    let val = paramValues.value[key]
    const mode = paramModes.value[key]
    paramModesOut[key] = mode
    fieldTypes[key] = field.type
    if (mode === 'var') {
      val = String(val || '').trim()
      if (val && !val.startsWith('@')) val = `@${val}`
    } else if (field.type === 'number') {
      val = val == null ? '' : String(val)
    } else {
      val = val == null ? '' : String(val)
    }
    if (field.required && !val) {
      return null
    }
    if (val !== '') params[key] = val
  }
  return { params, options: { paramModes: paramModesOut, fieldTypes } }
}

function normalizedParamValues() {
  const payload = buildInsertPayload()
  return payload?.params ?? null
}

function validateParams() {
  for (const field of pickedTool.value?.inputs || []) {
    if (!field.required) continue
    const val = paramValues.value[field.key]
    if (paramModes.value[field.key] === 'var') {
      if (!val || !String(val).replace(/^@/, '').trim()) {
        ElMessage.warning(`请选择或填写「${field.label}」引用的变量`)
        return false
      }
    } else if (val === '' || val == null) {
      ElMessage.warning(`请填写「${field.label}」`)
      return false
    }
  }
  return true
}

async function doInsert(toolId, params, options = {}) {
  const result = await insertDtToolRef(toolId, params, options)
  if (result?.ok) {
    const expr = formatDtToolRef(toolId, params, options)
    const tip =
      result.mode === 'copy'
        ? `已复制 ${expr}，请粘贴到目标输入框`
        : `已插入 ${expr}`
    ElMessage.success(tip)
    paramDialogVisible.value = false
  } else {
    ElMessage.warning('请先将光标放入要填入的输入框')
  }
}

function confirmInsert() {
  if (!pickedTool.value) return
  if (!validateParams()) return
  const payload = buildInsertPayload()
  if (!payload) return
  doInsert(pickedTool.value.id, payload.params, payload.options)
}
</script>

<style scoped lang="scss">
.tool-insert-panel {
  display: flex;
  flex-direction: column;
  max-height: 440px;
}

.tool-search {
  margin-bottom: 8px;
}

.tool-insert-tip {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin: 0 0 8px;
  line-height: 1.5;

  code {
    font-family: monospace;
    background: var(--el-fill-color-light);
    padding: 0 4px;
    border-radius: 3px;
  }
}

.tool-list {
  flex: 1;
  overflow-y: auto;
  min-height: 120px;
}

.tool-group-title {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  padding: 8px 8px 4px;
  border-top: 1px solid var(--el-border-color-lighter);

  .tool-group:first-child & {
    border-top: none;
    padding-top: 0;
  }
}

.tool-row {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 10px;
  cursor: pointer;
  border-radius: 4px;

  &:hover {
    background: var(--el-fill-color-light);
  }
}

.tool-name {
  font-size: 13px;
  font-weight: 500;
}

.tool-desc {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.tool-empty {
  padding: 24px;
  text-align: center;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.dialog-desc {
  margin: 0 0 12px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.param-tips {
  margin-bottom: 12px;

  .tips-list {
    margin: 4px 0 0;
    padding-left: 18px;
    font-size: 12px;
    line-height: 1.6;

    code {
      font-family: monospace;
      background: var(--el-fill-color-light);
      padding: 0 3px;
      border-radius: 3px;
    }
  }
}

.param-field {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.param-mode {
  align-self: flex-start;
}

.preview-expr {
  margin-top: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);

  code {
    font-family: monospace;
    word-break: break-all;
  }
}
</style>

<style lang="scss">
.tool-insert-popover.el-popover {
  padding: 12px !important;
}
</style>
