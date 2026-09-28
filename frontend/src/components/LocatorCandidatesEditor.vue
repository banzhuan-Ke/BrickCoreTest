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
            <el-tag v-if="primarySourceLabel" size="small" type="info" effect="plain">{{ primarySourceLabel }}</el-tag>
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
          <div v-if="!primaryLocator" class="lc-empty">暂无主定位</div>
          <div v-if="recommendedHint" class="lc-recommend">
            <el-tag size="small" type="warning" effect="plain">更稳推荐</el-tag>
            <span class="lc-recommend-src">{{ recommendedHint.sourceLabel }}</span>
            <el-tooltip
              :content="recommendedHint.locator"
              placement="top"
              :show-after="400"
              :disabled="recommendedHint.locator.length < 40"
              popper-class="lc-tooltip"
            >
              <code class="lc-recommend-code" @click="copyLocator(recommendedHint.locator)">{{ recommendedHint.locator }}</code>
            </el-tooltip>
            <el-button type="primary" link size="small" @click="adoptRecommended">采用推荐</el-button>
          </div>
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
          <div v-for="group in groupedList" :key="group.source" class="lc-group">
            <div class="lc-group-head">
              <span class="lc-group-label">{{ group.label }}</span>
              <el-tooltip
                v-if="group.tip"
                :content="group.tip"
                placement="top"
                :show-after="200"
              >
                <el-icon class="lc-group-help" :size="14"><QuestionFilled /></el-icon>
              </el-tooltip>
            </div>
            <ul class="lc-list">
              <li
                v-for="{ item, idx } in group.rows"
                :key="`${idx}-${candidateLocatorOf(item)}`"
                class="lc-item"
              >
                <span class="lc-idx">{{ idx + 1 }}</span>
                <div class="lc-main">
                  <el-tooltip
                    :content="candidateLocatorOf(item)"
                    placement="top"
                    :show-after="400"
                    :disabled="candidateLocatorOf(item).length < 48"
                    popper-class="lc-tooltip"
                  >
                    <code class="lc-code" @click="copyLocator(candidateLocatorOf(item))">{{ candidateLocatorOf(item) }}</code>
                  </el-tooltip>
                </div>
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
          </div>
        </template>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, EditPen, Plus, QuestionFilled } from '@element-plus/icons-vue'
import {
  LOCATOR_SOURCE_LABELS,
  LOCATOR_SOURCE_ORDER,
  LOCATOR_SOURCE_TIPS,
  candidateLocatorOf,
  candidateSourceOf,
  normalizeCandidates,
  normalizeLocatorValue,
  pickRecommendedCandidate,
  promoteToPrimary,
} from '@/utils/locatorCandidates.js'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  primary: { type: String, default: '' },
  primarySource: { type: String, default: 'current' },
  recommended: { type: Object, default: null },
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
  normalizeCandidates(props.modelValue, { excludePrimary: props.primary, keepObjects: true }),
)

const groupedList = computed(() => {
  const buckets = { current: [], elevated: [], neighbor: [], ai: [] }
  localList.value.forEach((item, idx) => {
    const src = candidateSourceOf(item)
    const row = { item, idx }
    if (buckets[src]) buckets[src].push(row)
    else buckets.current.push(row)
  })
  return LOCATOR_SOURCE_ORDER
    .filter((key) => buckets[key].length)
    .map((key) => ({
      source: key,
      label: LOCATOR_SOURCE_LABELS[key],
      tip: LOCATOR_SOURCE_TIPS[key] || '',
      rows: buckets[key],
    }))
})

const primaryLocator = computed(() => normalizeLocatorValue(props.primary))

const primarySourceLabel = computed(() => {
  const s = candidateSourceOf({ source: props.primarySource || 'current' })
  return LOCATOR_SOURCE_LABELS[s] || ''
})

const recommendedHint = computed(() => {
  const rec = props.recommended && props.recommended.locator
    ? props.recommended
    : pickRecommendedCandidate(localList.value, primaryLocator.value)
  if (!rec || !rec.locator) return null
  if (normalizeLocatorValue(rec.locator) === primaryLocator.value) return null
  return {
    locator: normalizeLocatorValue(rec.locator),
    source: candidateSourceOf(rec),
    sourceLabel: LOCATOR_SOURCE_LABELS[candidateSourceOf(rec)] || '',
    reason: rec.reason || '',
  }
})

watch(
  () => props.modelValue?.length,
  (n) => {
    if (n > 0 && !openNames.value.includes('backup')) {
      openNames.value = ['backup']
    }
  },
)

function emitList(list) {
  emit('update:modelValue', normalizeCandidates(list, { excludePrimary: props.primary, keepObjects: true }))
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
  draft.value = candidateLocatorOf(localList.value[idx]) || ''
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
    const prev = next[editingIndex.value]
    const prevLoc = candidateLocatorOf(prev)
    // 用户改了 locator 字符串后，不再沿用 elevated/neighbor/ai 来源
    const src = (prevLoc && prevLoc === loc && typeof prev === 'object' && prev.source)
      ? prev.source
      : 'current'
    next[editingIndex.value] = { locator: loc, source: src || 'current' }
  } else {
    if (next.some((x) => candidateLocatorOf(x) === loc)) {
      ElMessage.warning('该备用定位已存在')
      return
    }
    next.push({ locator: loc, source: 'current' })
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
  const result = promoteToPrimary(props.primary, localList.value, target, {
    primarySource: props.primarySource || 'current',
  })
  emit('promote', result)
  emit('update:modelValue', result.candidates)
  ElMessage.success('已切换主定位，原主定位已移入备用')
}

function adoptRecommended() {
  if (!recommendedHint.value) return
  const target = {
    locator: recommendedHint.value.locator,
    source: recommendedHint.value.source,
  }
  const result = promoteToPrimary(props.primary, localList.value, target, {
    primarySource: props.primarySource || 'current',
  })
  emit('promote', result)
  emit('update:modelValue', result.candidates)
  ElMessage.success('已采用更稳推荐作为主定位')
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

.lc-recommend {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed var(--el-border-color-lighter);
}

.lc-recommend-src {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.lc-recommend-code {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: pointer;
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

.lc-group {
  margin-bottom: 10px;
  padding: 8px 10px;
  border-radius: 6px;
  background: var(--el-fill-color-lighter);
  border: 1px solid var(--el-border-color-lighter);
}

.lc-group:last-child {
  margin-bottom: 0;
}

.lc-group-head {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 6px;
}

.lc-group-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.lc-group-help {
  color: var(--el-text-color-secondary);
  cursor: help;
}

.lc-group-help:hover {
  color: var(--el-color-primary);
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

.lc-main {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 6px;
}

.lc-source {
  flex-shrink: 0;
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
