<template>
  <div class="locator-candidates-editor">
    <el-collapse v-model="openNames" class="lc-collapse">
      <el-collapse-item name="backup">
        <template #title>
          <div class="lc-head">
            <span class="lc-title">备用定位</span>
            <el-tag size="small" type="info" effect="plain" round>{{ localList.length }}</el-tag>
            <span class="lc-hint">主定位在上方卡片，下列为备用</span>
            <el-button
              class="lc-head-add"
              size="small"
              type="primary"
              plain
              :icon="Plus"
              @click.stop="startAdd"
            >添加</el-button>
          </div>
        </template>

        <div v-if="primaryChangedHint" class="lc-warn">
          <span>主定位已改，请核对备用是否仍适用</span>
          <el-button type="danger" link size="small" @click="clearAll">清空</el-button>
        </div>

        <div class="lc-primary">
          <div class="lc-primary-meta">
            <el-tag size="small" type="success" effect="dark">当前主定位</el-tag>
            <span class="lc-primary-note">执行优先用它；失败后再依次试备用</span>
          </div>
          <el-tooltip
            v-if="primaryLocator"
            :content="primaryLocator"
            placement="top"
            :show-after="400"
            :disabled="primaryLocator.length < 48"
            popper-class="lc-tooltip"
          >
            <code class="lc-primary-code" @click="copyLocator(primaryLocator)">{{ primaryLocator }}</code>
          </el-tooltip>
          <div v-else class="lc-primary-empty">尚未填写，请在上方「元素定位表达式」中输入</div>
        </div>

        <div class="lc-section-label">
          <span>备用列表</span>
          <span class="lc-section-sub">不含主定位 · 共 {{ localList.length }} 条</span>
        </div>

        <div v-if="draftVisible" class="lc-draft">
          <div class="lc-draft-label">{{ editingIndex >= 0 ? '编辑备用定位' : '新增备用定位' }}</div>
          <el-input
            ref="draftInputRef"
            v-model="draft"
            type="textarea"
            :rows="2"
            placeholder="粘贴或输入定位表达式，例如 #submit 或 get_by_text=保存"
            resize="none"
            @keydown.ctrl.enter.exact="commitDraft"
          />
          <div class="lc-draft-actions">
            <el-button size="small" type="primary" @click="commitDraft">保存</el-button>
            <el-button size="small" @click="cancelDraft">取消</el-button>
            <span class="lc-draft-tip">Ctrl+Enter 保存</span>
          </div>
        </div>

        <div v-if="!localList.length && !draftVisible" class="lc-empty">
          <p class="lc-empty-text">暂无备用。可将上方主定位的替代写法加在这里，或由定位助手写入</p>
          <el-button size="small" type="primary" :icon="Plus" @click="startAdd">添加备用定位</el-button>
        </div>

        <template v-else-if="localList.length">
          <div class="lc-toolbar">
            <el-button size="small" type="primary" plain :icon="Plus" @click="startAdd">继续添加</el-button>
            <el-button size="small" plain @click="clearAll">清空全部</el-button>
          </div>
          <ul class="lc-list">
            <li v-for="(item, idx) in localList" :key="`${idx}-${item}`" class="lc-item">
              <span class="lc-idx">{{ idx + 1 }}</span>
              <el-tooltip
                :content="item"
                placement="top"
                :show-after="400"
                :disabled="item.length < 48"
                popper-class="lc-tooltip"
              >
                <code class="lc-code" @click="copyLocator(item)">{{ item }}</code>
              </el-tooltip>
              <div class="lc-actions">
                <el-tooltip content="提升为主定位（原主定位会进入备用）" placement="top" :show-after="300">
                  <el-button type="primary" link size="small" @click="promote(idx)">设为主</el-button>
                </el-tooltip>
                <el-tooltip content="编辑" placement="top" :show-after="300">
                  <el-button type="primary" link size="small" :icon="EditPen" @click="startEdit(idx)" />
                </el-tooltip>
                <el-tooltip content="删除" placement="top" :show-after="300">
                  <el-button type="danger" link size="small" :icon="Delete" @click="removeAt(idx)" />
                </el-tooltip>
              </div>
            </li>
          </ul>
        </template>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, EditPen, Plus } from '@element-plus/icons-vue'
import {
  normalizeCandidates,
  normalizeLocatorValue,
  promoteToPrimary,
} from '@/utils/locatorCandidates.js'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  primary: { type: String, default: '' },
  primaryChangedHint: { type: Boolean, default: false },
  defaultExpand: { type: Boolean, default: true },
})

const emit = defineEmits(['update:modelValue', 'promote'])

const openNames = ref(props.defaultExpand ? ['backup'] : [])
const draftVisible = ref(false)
const draft = ref('')
const editingIndex = ref(-1)
const draftInputRef = ref(null)

const localList = computed(() =>
  normalizeCandidates(props.modelValue, { excludePrimary: props.primary }),
)

const primaryLocator = computed(() => normalizeLocatorValue(props.primary))

watch(
  () => props.modelValue?.length,
  (n) => {
    if (n > 0 && !openNames.value.includes('backup')) {
      openNames.value = ['backup']
    }
  },
)

function emitList(list) {
  emit('update:modelValue', normalizeCandidates(list, { excludePrimary: props.primary }))
}

async function focusDraft() {
  await nextTick()
  const el = draftInputRef.value?.textarea || draftInputRef.value?.$el?.querySelector?.('textarea')
  el?.focus?.()
}

function startAdd() {
  if (!openNames.value.includes('backup')) {
    openNames.value = ['backup']
  }
  editingIndex.value = -1
  draft.value = ''
  draftVisible.value = true
  focusDraft()
}

function startEdit(idx) {
  if (!openNames.value.includes('backup')) {
    openNames.value = ['backup']
  }
  editingIndex.value = idx
  draft.value = localList.value[idx] || ''
  draftVisible.value = true
  focusDraft()
}

function cancelDraft() {
  draftVisible.value = false
  draft.value = ''
  editingIndex.value = -1
}

function commitDraft() {
  const loc = normalizeLocatorValue(draft.value)
  if (!loc) {
    ElMessage.warning('请填写定位表达式')
    return
  }
  const primary = normalizeLocatorValue(props.primary)
  if (primary && loc === primary) {
    ElMessage.warning('与主定位相同，无需加入备用')
    return
  }
  const wasEdit = editingIndex.value >= 0
  const next = [...localList.value]
  if (wasEdit) {
    next[editingIndex.value] = loc
  } else {
    if (next.includes(loc)) {
      ElMessage.warning('该备用定位已存在')
      return
    }
    next.push(loc)
  }
  emitList(next)
  cancelDraft()
  ElMessage.success(wasEdit ? '已更新备用定位' : '已添加备用定位')
}

function removeAt(idx) {
  emitList(localList.value.filter((_, i) => i !== idx))
}

async function clearAll() {
  if (!localList.value.length) return
  try {
    await ElMessageBox.confirm('确定清空全部备用定位？', '提示', { type: 'warning' })
  } catch {
    return
  }
  emitList([])
  cancelDraft()
}

function promote(idx) {
  const target = localList.value[idx]
  if (!target) return
  const { primary, candidates } = promoteToPrimary(props.primary, localList.value, target)
  emit('promote', { primary, candidates })
  emit('update:modelValue', candidates)
  ElMessage.success('已切换主定位，原主定位已移入备用')
}

async function copyLocator(text) {
  const v = String(text || '').trim()
  if (!v) return
  try {
    await navigator.clipboard.writeText(v)
    ElMessage.success('已复制定位')
  } catch {
    /* ignore */
  }
}
</script>

<style scoped>
.locator-candidates-editor {
  margin-top: 10px;
  width: 100%;
}

.lc-collapse {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-fill-color-blank);
  overflow: hidden;
}

.lc-collapse :deep(.el-collapse-item__header) {
  height: auto;
  min-height: 40px;
  line-height: 1.4;
  padding: 8px 12px;
  border-bottom: none;
  background: var(--el-fill-color-light);
}

.lc-collapse :deep(.el-collapse-item__wrap) {
  border-top: 1px solid var(--el-border-color-extra-light);
}

.lc-collapse :deep(.el-collapse-item__content) {
  padding: 10px 12px 12px;
}

.lc-collapse :deep(.el-collapse-item__arrow) {
  margin-right: 4px;
}

.lc-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
  padding-right: 8px;
}

.lc-title {
  font-weight: 600;
  font-size: 13px;
  color: var(--el-text-color-primary);
}

.lc-hint {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  font-weight: normal;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-right: auto;
}

.lc-head-add {
  flex-shrink: 0;
}

.lc-warn {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
  padding: 8px 10px;
  font-size: 12px;
  color: var(--el-color-warning-dark-2);
  background: var(--el-color-warning-light-9);
  border-radius: 6px;
}

.lc-primary {
  margin-bottom: 12px;
  padding: 10px 12px;
  border-radius: 6px;
  background: var(--el-color-success-light-9);
  border: 1px solid var(--el-color-success-light-5);
}

.lc-primary-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  flex-wrap: wrap;
}

.lc-primary-note {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.lc-primary-code {
  display: block;
  margin: 0;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  line-height: 1.45;
  color: var(--el-text-color-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  cursor: pointer;
}

.lc-primary-code:hover {
  color: var(--el-color-primary);
}

.lc-primary-empty {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.lc-section-label {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.lc-section-sub {
  font-size: 12px;
  font-weight: normal;
  color: var(--el-text-color-secondary);
}

.lc-toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
}

.lc-draft {
  margin-bottom: 10px;
  padding: 10px;
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
  border: 1px dashed var(--el-color-primary-light-5);
}

.lc-draft-label {
  margin-bottom: 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--el-text-color-regular);
}

.lc-draft-actions {
  margin-top: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.lc-draft-tip {
  margin-left: auto;
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}

.lc-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 16px 8px;
  text-align: center;
}

.lc-empty-text {
  margin: 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}

.lc-list {
  list-style: none;
  margin: 0;
  padding: 0;
  max-height: 220px;
  overflow-y: auto;
  border: 1px solid var(--el-border-color-extra-light);
  border-radius: 6px;
  background: #fff;
}

.lc-item {
  display: grid;
  grid-template-columns: 22px minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  border-bottom: 1px solid var(--el-border-color-extra-light);
  transition: background 0.15s ease;
}

.lc-item:last-child {
  border-bottom: none;
}

.lc-item:hover {
  background: var(--el-fill-color-lighter);
}

.lc-idx {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  color: var(--el-text-color-secondary);
  background: var(--el-fill-color);
  flex-shrink: 0;
}

.lc-code {
  display: block;
  min-width: 0;
  margin: 0;
  padding: 0;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  line-height: 1.4;
  color: var(--el-text-color-regular);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  cursor: pointer;
}

.lc-code:hover {
  color: var(--el-color-primary);
}

.lc-actions {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
}

.lc-actions :deep(.el-button) {
  padding: 0 4px;
  min-height: auto;
}
</style>

<style>
.lc-tooltip {
  max-width: min(480px, 80vw) !important;
  word-break: break-all;
  line-height: 1.45;
  font-size: 12px;
}
</style>
