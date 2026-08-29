<template>
  <el-popover
    trigger="click"
    placement="bottom-start"
    :width="440"
    popper-class="var-insert-popover"
    @show="onPopoverShow"
  >
    <template #reference>
      <el-button
        :size="size"
        :type="type"
        :link="link"
        :icon="Promotion"
        @mousedown="onReferenceMouseDown"
      >
        {{ label }}
      </el-button>
    </template>

    <div class="var-insert-panel">
      <el-input
        v-model="searchKeyword"
        placeholder="搜索变量名 / 预览 / 分组"
        clearable
        size="small"
        prefix-icon="Search"
        class="var-search"
      />
      <p v-if="hintText" class="var-insert-hint">{{ hintText }}</p>
      <div class="var-list" @click="onListClick">
        <template v-if="groupedFiltered.length">
          <div v-for="(block, bi) in groupedFiltered" :key="bi" class="var-group">
            <div class="var-group-title">{{ block.group }}</div>
            <div
              v-for="item in block.items"
              :key="item.uid"
              class="var-row"
              :class="{ disabled: item.disabled }"
              :data-command="item.disabled ? '' : item.command"
            >
              <div class="var-row-main">
                <span class="var-key">{{ item.key }}</span>
                <span v-if="item.preview" class="var-preview">{{ item.preview }}</span>
              </div>
              <el-tooltip
                v-if="item.description"
                :content="item.description"
                placement="top"
                :show-after="200"
                :disabled="item.disabled"
              >
                <span class="var-desc">{{ item.description }}</span>
              </el-tooltip>
            </div>
          </div>
        </template>
        <div v-else class="var-empty">无匹配变量</div>
      </div>
      <div v-if="showEnvEdit && envId" class="var-footer">
        <el-button type="primary" link size="small" @click.stop="openEnvVarEdit">
          管理环境变量…
        </el-button>
      </div>
    </div>
  </el-popover>

  <EnvVarQuickEdit v-model="envVarEditVisible" :env-id="envId" />
</template>

<script setup>
import { computed, ref } from 'vue'
import { Promotion } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { httpAuthConfigApi } from '@/api/modules/httpAuth'
import { BUILTIN_VAR_HINTS, isSecretKey, stripSystemGlobalVars, varsObjectToList } from '@/utils/globalVars.js'
import { insertVarRef, snapshotInsertTarget } from '@/utils/varInsert.js'
import EnvVarQuickEdit from '@/components/EnvVarQuickEdit.vue'
// 变量源约定与 ToolInsertButton 一致：项目/环境/授权/内置/extra；
// 扁平分组构建见 @/utils/insertableVars.js（插入工具引用变量已复用）。

const props = defineProps({
  envId: { type: Number, default: null },
  extraVars: { type: Array, default: () => [] },
  label: { type: String, default: '插入变量' },
  size: { type: String, default: 'small' },
  type: { type: String, default: 'primary' },
  link: { type: Boolean, default: true },
  showEnvEdit: { type: Boolean, default: true },
  /** 底部说明（可选） */
  hintText: { type: String, default: '' },
})

const emit = defineEmits(['edit-env-vars'])

const proStore = ProjectStore()
const envVarEditVisible = ref(false)
const builtinHints = BUILTIN_VAR_HINTS
const searchKeyword = ref('')
const authPreview = ref({ auth_name: null, is_enabled: false, items: [] })
const authLoading = ref(false)
let uidSeq = 0

function onReferenceMouseDown() {
  snapshotInsertTarget()
}

async function loadAuthVariables() {
  const projectId = proStore.projectInfo?.id
  if (!projectId || !props.envId) {
    authPreview.value = { auth_name: null, is_enabled: false, items: [] }
    return
  }
  authLoading.value = true
  try {
    const res = await httpAuthConfigApi.getVariablesPreview(projectId, props.envId)
    const data = res.data?.data ?? res.data ?? {}
    authPreview.value = {
      auth_name: data.auth_name ?? null,
      is_enabled: Boolean(data.is_enabled),
      items: Array.isArray(data.items) ? data.items : [],
    }
  } catch {
    authPreview.value = { auth_name: null, is_enabled: false, items: [] }
  } finally {
    authLoading.value = false
  }
}

function onPopoverShow() {
  searchKeyword.value = ''
  snapshotInsertTarget()
  loadAuthVariables()
}

function openEnvVarEdit() {
  envVarEditVisible.value = true
  emit('edit-env-vars')
}

const projectVars = computed(() => {
  const gv = proStore.projectInfo?.global_vars
  return varsObjectToList(stripSystemGlobalVars(gv && typeof gv === 'object' ? gv : {})).filter(
    (r) => !r._rawObject
  )
})

const envVars = computed(() => {
  if (!props.envId) return []
  const env = proStore.envList.find((e) => e.id === props.envId)
  return varsObjectToList(stripSystemGlobalVars(env?.global_vars || {})).filter((r) => !r._rawObject)
})

function previewValue(value, key = '') {
  if (value === null || value === undefined || value === '') return ''
  if (key && isSecretKey(key)) return '••••••'
  if (typeof value === 'object') {
    try {
      const s = JSON.stringify(value)
      return s.length > 28 ? s.slice(0, 28) + '…' : s
    } catch {
      return '[Object]'
    }
  }
  const s = String(value)
  return s.length > 28 ? s.slice(0, 28) + '…' : s
}

function makeItem(group, key, command, preview, disabled = false, description = '') {
  return {
    uid: ++uidSeq,
    group,
    key,
    command,
    preview,
    description,
    disabled,
  }
}

const allItems = computed(() => {
  const items = []
  for (const item of projectVars.value) {
    if (item._rawObject) continue
    items.push(makeItem('项目变量', item.key, item.key, previewValue(item.value), false, item.description))
  }
  if (props.envId) {
    for (const item of envVars.value) {
      if (item._rawObject) continue
      items.push(makeItem('环境变量', item.key, item.key, previewValue(item.value), false, item.description))
    }
    if (!envVars.value.length) {
      items.push(makeItem('环境变量', '当前环境暂无变量', '', '', true))
    }
    if (authLoading.value) {
      items.push(makeItem('Token 授权', '加载中…', '', '', true))
    } else if (authPreview.value.items.length) {
      const suffix = authPreview.value.is_enabled ? '' : '（未启用，执行时不注入）'
      for (const item of authPreview.value.items) {
        const desc = `${item.description || ''}${suffix}`.trim()
        items.push(
          makeItem('Token 授权', item.name, item.name, previewValue(item.preview, item.name), false, desc)
        )
      }
    } else {
      items.push(makeItem('Token 授权', '当前环境未配置授权', '', '', true))
    }
  } else {
    items.push(makeItem('环境变量', '请先选择参考环境', '', '', true))
    items.push(makeItem('Token 授权', '请先选择参考环境', '', '', true))
  }
  for (const item of builtinHints) {
    items.push(makeItem('内置变量', item.key, item.key, item.label))
  }
  for (const key of props.extraVars) {
    if (key) items.push(makeItem('本用例变量', key, key, ''))
  }
  return items
})

const filteredItems = computed(() => {
  const q = searchKeyword.value.trim().toLowerCase()
  if (!q) return allItems.value
  return allItems.value.filter((item) => {
    if (item.disabled) return false
    const hay = `${item.group} ${item.key} ${item.description} ${item.preview}`.toLowerCase()
    return hay.includes(q)
  })
})

const groupedFiltered = computed(() => {
  const order = []
  const map = new Map()
  for (const item of filteredItems.value) {
    if (!map.has(item.group)) {
      map.set(item.group, [])
      order.push(item.group)
    }
    map.get(item.group).push(item)
  }
  return order.map((group) => ({ group, items: map.get(group) }))
})

function onListClick(e) {
  const row = e.target.closest('.var-row')
  if (!row || row.classList.contains('disabled')) return
  const command = row.dataset.command
  if (command) onInsert(command)
}

async function onInsert(command) {
  const result = await insertVarRef(command)
  if (result?.ok) {
    const tip =
      result.mode === 'copy'
        ? `已复制 ${formatDisplay(command)}，请粘贴到输入框`
        : `已插入 ${formatDisplay(command)}`
    ElMessage.success(tip)
  } else {
    ElMessage.warning('请先将光标放入输入框')
  }
}

function formatDisplay(name) {
  return `\${{${name}}}`
}
</script>

<style scoped lang="scss">
.var-insert-panel {
  display: flex;
  flex-direction: column;
  max-height: 420px;
}

.var-search {
  margin-bottom: 8px;
  flex-shrink: 0;
}

.var-insert-hint {
  margin: 0 0 8px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--el-text-color-secondary);
}

.var-list {
  flex: 1;
  overflow-y: auto;
  min-height: 120px;
  max-height: 360px;
}

.var-group-title {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  padding: 8px 8px 4px;
  border-top: 1px solid var(--el-border-color-lighter);

  .var-group:first-child & {
    border-top: none;
    padding-top: 0;
  }
}

.var-row {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 2px;
  padding: 8px 10px;
  cursor: pointer;
  border-radius: 4px;
  font-size: 13px;

  &:hover:not(.disabled) {
    background: var(--el-fill-color-light);
  }

  &.disabled {
    cursor: default;
    color: var(--el-text-color-placeholder);
  }
}

.var-row-main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-width: 0;
}

.var-key {
  font-family: monospace;
  flex-shrink: 0;
}

.var-desc {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow: hidden;
  word-break: break-word;
}

.var-preview {
  color: var(--el-text-color-placeholder);
  font-size: 12px;
  flex-shrink: 1;
  min-width: 0;
  max-width: 55%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-align: right;
}

.var-empty {
  padding: 24px;
  text-align: center;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.var-footer {
  border-top: 1px solid var(--el-border-color-lighter);
  padding-top: 6px;
  margin-top: 4px;
  flex-shrink: 0;
}
</style>

<style lang="scss">
.var-insert-popover.el-popover {
  padding: 12px !important;
}
</style>
