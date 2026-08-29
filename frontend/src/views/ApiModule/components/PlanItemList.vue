<template>
  <div class="plan-item-list">
    <div class="list-header">
      <span class="list-title">计划内容（{{ localItems.length }} 项）</span>
      <span class="list-hint">拖拽调整顺序 · 链接图标设置前置依赖</span>
    </div>

    <VueDraggable
      v-model="localItems"
      :animation="200"
      handle=".drag-handle"
      class="draggable-list"
      @end="emitChange"
    >
      <div
        v-for="(item, index) in localItems"
        :key="item._key || item.id || index"
        class="item-row"
      >
        <!-- 序号 -->
        <span class="exec-order">{{ index + 1 }}</span>

        <!-- 拖拽把手 -->
        <el-icon class="drag-handle"><Rank /></el-icon>

        <!-- 类型标签 -->
        <el-tag
          size="small"
          :type="item.item_type === 'suite' ? 'warning' : 'primary'"
          style="flex-shrink: 0; margin-right: 6px"
        >
          {{ item.item_type === 'suite' ? '套件' : '用例' }}
        </el-tag>

        <!-- 接口方法（用例时展示） -->
        <el-tag
          v-if="item.item_type === 'case' && item.api_method"
          size="small"
          :type="methodType(item.api_method)"
          style="flex-shrink: 0; margin-right: 6px"
        >
          {{ item.api_method }}
        </el-tag>

        <!-- 名称 -->
        <span class="item-name" :title="displayName(item)">{{ displayName(item) }}</span>

        <!-- 接口名（用例时） -->
        <span v-if="item.item_type === 'case' && item.api_name" class="item-api">
          / {{ item.api_name }}
        </span>

        <!-- 依赖标签 -->
        <div v-if="item.depends_on && item.depends_on.length > 0" class="dep-tags">
          <el-tag
            v-for="depId in item.depends_on"
            :key="depId"
            size="small"
            type="info"
            closable
            @close="removeDepFromItem(index, depId)"
          >
            #{{ getItemOrder(depId) }} {{ getItemName(depId) }}
          </el-tag>
        </div>

        <!-- 操作 -->
        <div class="row-actions">
          <el-button link type="info" @click="openDepDialog(index)" title="设置依赖">
            <el-icon><Connection /></el-icon>
          </el-button>
          <el-button link @click="moveUp(index)" :disabled="index === 0" title="上移">
            <el-icon><ArrowUp /></el-icon>
          </el-button>
          <el-button link @click="moveDown(index)" :disabled="index === localItems.length - 1" title="下移">
            <el-icon><ArrowDown /></el-icon>
          </el-button>
          <el-button link type="danger" @click="removeAt(index)" title="移除">
            <el-icon><Delete /></el-icon>
          </el-button>
        </div>
      </div>
    </VueDraggable>

    <el-empty
      v-if="localItems.length === 0"
      description="暂无内容，请从左侧添加套件或用例"
      :image-size="80"
    />
  </div>

  <!-- 依赖设置弹窗 -->
  <el-dialog
    v-model="depDialogVisible"
    title="设置前置依赖"
    width="480px"
    :close-on-click-modal="false"
  >
    <div v-if="editingIndex !== null" class="dep-dialog-tip">
      <p>
        当前项：<strong>#{{ editingIndex + 1 }} {{ displayName(localItems[editingIndex]) }}</strong>
      </p>
      <p>
        前置依赖表示：在<strong>串行执行</strong>时，若所选前序项执行失败，则<strong>跳过</strong>当前项（不执行）。
        仅可选择序号小于当前项的前序项。
      </p>
      <p class="dep-dialog-tip-muted">
        提示：这不会自动调整执行顺序；列表顺序仍决定实际执行先后。变量传递由前序项向后续项链式继承。
      </p>
    </div>
    <el-empty
      v-if="depCandidates.length === 0"
      description="当前是第 1 项，没有可依赖的前序项。请先在左侧再添加套件/用例，再对后面的项设置依赖。"
      :image-size="64"
    />
    <el-select
      v-else
      v-model="editingDeps"
      multiple
      collapse-tags
      collapse-tags-tooltip
      placeholder="选择前置项（可多选，仅限前序项）"
      style="width:100%"
    >
      <el-option
        v-for="(candidate, idx) in depCandidates"
        :key="candidate._key || candidate.id || idx"
        :label="`#${getItemOrder(candidate._key || candidate.id)} ${displayName(candidate)}`"
        :value="candidate._key || candidate.id"
      />
    </el-select>
    <template #footer>
      <el-button @click="depDialogVisible = false">取消</el-button>
      <el-button type="primary" @click="confirmDeps">确认</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, watch, computed } from 'vue'
import { VueDraggable } from 'vue-draggable-plus'
import { Rank, Delete, ArrowUp, ArrowDown, Connection } from '@element-plus/icons-vue'

const props = defineProps({
  items: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['update:items'])

// 本地副本，加 _key 防止 key 冲突
const localItems = ref([])

let _keyCounter = 0
const withKey = (item) => ({
  ...item,
  _key: item._key || `item_${++_keyCounter}_${Date.now()}`
})

watch(
  () => props.items,
  (val) => {
    const withKeys = val.map(withKey)
    const refToKey = {}
    withKeys.forEach((it) => {
      if (it._key) refToKey[it._key] = it._key
      if (it.id != null) {
        refToKey[it.id] = it._key
        refToKey[String(it.id)] = it._key
      }
    })
    localItems.value = withKeys.map((it) => ({
      ...it,
      depends_on: (it.depends_on || [])
        .map((dep) => refToKey[dep] ?? refToKey[String(dep)])
        .filter(Boolean),
    }))
  },
  { immediate: true, deep: true }
)

const emitChange = () => {
  // 更新 sort 值
  const updated = localItems.value.map((item, idx) => ({ ...item, sort: idx }))
  localItems.value = updated
  emit('update:items', updated)
}

const moveUp = (index) => {
  if (index === 0) return
  const arr = [...localItems.value]
  ;[arr[index - 1], arr[index]] = [arr[index], arr[index - 1]]
  localItems.value = arr
  emitChange()
}

const moveDown = (index) => {
  if (index === localItems.value.length - 1) return
  const arr = [...localItems.value]
  ;[arr[index], arr[index + 1]] = [arr[index + 1], arr[index]]
  localItems.value = arr
  emitChange()
}

const removeAt = (index) => {
  localItems.value.splice(index, 1)
  emitChange()
}

const displayName = (item) => {
  if (item.item_type === 'suite') return item.suite_name || `套件 #${item.suite_id}`
  return item.case_name || `用例 #${item.case_id}`
}

const methodType = (m) => {
  const map = { GET: 'success', POST: 'primary', PUT: 'warning', DELETE: 'danger', PATCH: 'warning' }
  return map[m] || 'info'
}

// ===== 依赖管理 =====
const depDialogVisible = ref(false)
const editingIndex = ref(null)
const editingDeps = ref([])

// 候选列表：仅当前 item 之前的前序项
const depCandidates = computed(() => {
  if (editingIndex.value === null) return []
  return localItems.value.filter((_, idx) => idx < editingIndex.value)
})

// 根据 _key/id 获取 item 的序号（1-based）
const getItemOrder = (keyOrId) => {
  const idx = localItems.value.findIndex(
    it => it._key === keyOrId || it.id === keyOrId
  )
  return idx >= 0 ? idx + 1 : '?'
}

// 根据 _key/id 获取 item 的显示名称
const getItemName = (keyOrId) => {
  const it = localItems.value.find(it => it._key === keyOrId || it.id === keyOrId)
  return it ? displayName(it) : `#${keyOrId}`
}

// 打开依赖弹窗
const openDepDialog = (index) => {
  editingIndex.value = index
  const item = localItems.value[index]
  // depends_on 存储 _key 或 id；回显时需要匹配
  editingDeps.value = (item.depends_on || []).filter(v => {
    return localItems.value.some(it => it._key === v || it.id === v)
  })
  depDialogVisible.value = true
}

// 确认设置依赖
const confirmDeps = () => {
  if (editingIndex.value === null) return
  localItems.value[editingIndex.value] = {
    ...localItems.value[editingIndex.value],
    depends_on: [...editingDeps.value],
  }
  depDialogVisible.value = false
  emitChange()
}

// 从 tag 关闭删除单个依赖
const removeDepFromItem = (index, keyOrId) => {
  const item = localItems.value[index]
  localItems.value[index] = {
    ...item,
    depends_on: (item.depends_on || []).filter(v => v !== keyOrId),
  }
  emitChange()
}
</script>

<style scoped>
.plan-item-list {
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  min-height: 120px;
}
.list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  background: var(--el-fill-color-lighter);
  border-radius: 6px 6px 0 0;
}
.list-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.list-hint {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}
.draggable-list {
  padding: 4px 0;
}
.item-row {
  display: flex;
  align-items: center;
  padding: 8px 12px;
  border-bottom: 1px solid var(--el-border-color-extra-light);
  transition: background 0.15s;
  gap: 4px;
}
.item-row:last-child {
  border-bottom: none;
}
.item-row:hover {
  background: var(--el-fill-color-light);
}
.exec-order {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--el-color-primary-light-7);
  color: var(--el-color-primary);
  font-size: 12px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-right: 4px;
}
.drag-handle {
  cursor: move;
  color: var(--el-text-color-placeholder);
  font-size: 16px;
  flex-shrink: 0;
  margin-right: 4px;
}
.drag-handle:hover {
  color: var(--el-color-primary);
}
.item-name {
  flex: 1;
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
.item-api {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-left: 4px;
  flex-shrink: 0;
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.row-actions {
  display: flex;
  align-items: center;
  flex-shrink: 0;
  margin-left: 4px;
}
.dep-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  flex-shrink: 0;
  margin-left: 4px;
}
.dep-dialog-tip {
  margin-bottom: 12px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
  line-height: 1.6;

  p {
    margin: 0 0 8px;
  }
}
.dep-dialog-tip-muted {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}
</style>
