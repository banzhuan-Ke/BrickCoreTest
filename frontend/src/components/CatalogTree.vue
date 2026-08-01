<template>
  <div class="catalog-tree" :class="{ 'catalog-tree--fill': fillHeight }">
    <div class="tree-header">
      <span class="tree-title">测试目录</span>
      <el-button
        v-if="showManage"
        type="primary"
        link
        size="small"
        icon="Plus"
        title="新建目录"
        @click="openCreateDialog(null)"
      />
    </div>

    <el-input
      v-if="showSearch"
      v-model="filterText"
      placeholder="搜索目录"
      clearable
      size="small"
      prefix-icon="Search"
      class="tree-search"
    />

    <el-tree
      ref="treeRef"
      v-loading="loading"
      :data="treeData"
      :props="{ label: 'name', children: 'children' }"
      node-key="id"
      highlight-current
      :default-expand-all="defaultExpandAll"
      :current-node-key="currentKey"
      :filter-node-method="filterNode"
      class="catalog-tree-inner"
      @node-click="handleNodeClick"
    >
      <template #default="{ node, data }">
        <span
          class="tree-node"
          :class="{ 'is-all-node': data.id === 'all' }"
        >
          <el-icon class="node-icon">
            <FolderOpened v-if="data.id === 'all'" />
            <Folder v-else-if="!node.expanded || !data.children?.length" />
            <FolderOpened v-else />
          </el-icon>
          <span class="node-label" :title="node.label">{{ node.label }}</span>
          <span v-if="badgeForNode(data)" class="node-badge">{{ badgeForNode(data) }}</span>
          <span v-if="showManage && data.id !== 'all'" class="node-actions">
            <el-button type="primary" link size="small" icon="Plus" title="新建子目录" @click.stop="openCreateDialog(data.id)" />
            <el-button type="primary" link size="small" icon="Edit" title="编辑" @click.stop="openEditDialog(data)" />
            <el-button type="danger" link size="small" icon="Delete" title="删除" @click.stop="handleDelete(data)" />
          </span>
        </span>
      </template>
    </el-tree>

    <el-dialog
      v-model="dialog.visible"
      :title="dialog.isEdit ? '编辑目录' : '新建目录'"
      width="420px"
      destroy-on-close
      append-to-body
    >
      <el-form :model="dialog.form" label-width="80px">
        <el-form-item label="目录名称" required>
          <el-input v-model="dialog.form.name" placeholder="请输入目录名称" @keyup.enter="saveCatalog" />
        </el-form-item>
        <el-form-item label="上级目录">
          <el-tree-select
            v-model="dialog.form.parent_id"
            :data="parentTreeOptions"
            :props="{ label: 'name', value: 'id', children: 'children' }"
            clearable
            check-strictly
            placeholder="根目录"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="dialog.form.sort" :min="0" style="width: 100%" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="dialog.form.description" type="textarea" rows="2" placeholder="可选" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="dialog.saving" @click="saveCatalog">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue'
import { Folder, FolderOpened } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { catalogApi, buildCatalogTree } from '@/api/modules/catalog'

const props = defineProps({
  projectId: {
    type: [Number, String],
    default: null
  },
  modelValue: {
    type: [Number, String, null],
    default: null
  },
  showManage: {
    type: Boolean,
    default: false
  },
  includeAllNode: {
    type: Boolean,
    default: true
  },
  allNodeLabel: {
    type: String,
    default: '全部'
  },
  defaultExpandAll: {
    type: Boolean,
    default: false
  },
  /** 目录 id -> 资产数量，用于节点徽章 */
  countMap: {
    type: Object,
    default: () => ({})
  },
  /** 是否显示搜索框 */
  showSearch: {
    type: Boolean,
    default: false
  },
  /** 是否撑满父容器高度 */
  fillHeight: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:modelValue', 'change', 'loaded', 'changed'])

const treeRef = ref()
const loading = ref(false)
const rawTree = ref([])
const filterText = ref('')

const currentKey = computed(() => props.modelValue ?? (props.includeAllNode ? 'all' : null))

const treeData = computed(() => {
  const nodes = rawTree.value
  if (!props.includeAllNode) return nodes
  return [{ id: 'all', name: props.allNodeLabel, children: [] }, ...nodes]
})

const parentTreeOptions = computed(() => {
  const filterTree = (items) => {
    return items
      .filter(item => item.id !== 'all' && item.id !== dialog.form.id)
      .map(item => ({
        ...item,
        children: item.children?.length ? filterTree(item.children) : []
      }))
  }
  return filterTree(rawTree.value)
})

const dialog = reactive({
  visible: false,
  isEdit: false,
  saving: false,
  form: {
    id: null,
    name: '',
    parent_id: null,
    sort: 0,
    description: ''
  }
})

const normalizeTreeResponse = (data) => {
  if (!Array.isArray(data)) return []
  const hasNested = data.some(item => Array.isArray(item.children) && item.children.length > 0)
  return hasNested ? data : buildCatalogTree(data)
}

const badgeMap = computed(() => {
  const map = {}
  const countOf = (id) => props.countMap[id] ?? props.countMap[String(id)] ?? 0
  const sumSubtree = (node) => {
    if (!node || node.id === 'all') return 0
    let total = countOf(node.id)
    for (const child of node.children || []) {
      total += sumSubtree(child)
    }
    return total
  }
  const walk = (nodes) => {
    for (const node of nodes) {
      if (node.id === 'all') {
        const total = Object.values(props.countMap).reduce((a, b) => a + (b || 0), 0)
        if (total > 0) map.all = total
      } else {
        const count = sumSubtree(node)
        if (count > 0) map[node.id] = count
      }
      if (node.children?.length) walk(node.children)
    }
  }
  walk(treeData.value)
  return map
})

const badgeForNode = (data) => {
  const id = data?.id
  if (id == null) return null
  return badgeMap.value[id] ?? badgeMap.value[String(id)] ?? null
}

const filterNode = (value, data) => {
  if (!value) return true
  return (data.name || '').toLowerCase().includes(value.toLowerCase())
}

watch(filterText, (val) => {
  treeRef.value?.filter(val)
})

const loadTree = async () => {
  if (!props.projectId) {
    rawTree.value = []
    return
  }
  loading.value = true
  try {
    const res = await catalogApi.getList({ project_id: props.projectId, tree: true })
    if (res.status === 200) {
      rawTree.value = normalizeTreeResponse(res.data)
      emit('loaded', rawTree.value)
    }
  } catch (error) {
    console.error('加载测试目录失败:', error)
    rawTree.value = []
  } finally {
    loading.value = false
  }
}

watch(
  () => props.projectId,
  () => loadTree(),
  { immediate: true }
)

watch(
  () => props.modelValue,
  (val) => {
    if (treeRef.value && val != null) {
      treeRef.value.setCurrentKey(val)
    } else if (treeRef.value && props.includeAllNode) {
      treeRef.value.setCurrentKey('all')
    }
  }
)

const handleNodeClick = (data) => {
  const id = data.id === 'all' ? null : data.id
  emit('update:modelValue', id)
  emit('change', id, data)
}

const resetDialogForm = () => {
  dialog.form.id = null
  dialog.form.name = ''
  dialog.form.parent_id = null
  dialog.form.sort = 0
  dialog.form.description = ''
}

const openCreateDialog = (parentId = null) => {
  dialog.isEdit = false
  resetDialogForm()
  dialog.form.parent_id = parentId
  dialog.visible = true
}

const openEditDialog = (data) => {
  dialog.isEdit = true
  dialog.form.id = data.id
  dialog.form.name = data.name
  dialog.form.parent_id = data.parent_id ?? null
  dialog.form.sort = data.sort ?? 0
  dialog.form.description = data.description ?? ''
  dialog.visible = true
}

const hasChildren = (catalogId) => {
  const walk = (nodes) => {
    for (const node of nodes) {
      if (node.id === catalogId && node.children?.length) return true
      if (node.children?.length && walk(node.children)) return true
    }
    return false
  }
  return walk(rawTree.value)
}

const handleDelete = async (data) => {
  try {
    const cascade = hasChildren(data.id)
    const assetHint = badgeForNode(data)
    let message = cascade
      ? '该目录下存在子目录，是否一并删除？'
      : '确认删除该目录吗？'
    if (assetHint) {
      message += `\n\n注意：目录（含子目录）下仍有约 ${assetHint} 项资产。若仍有接口/用例等，删除会被拒绝，请先移出或删除资产。`
    } else {
      message += '\n\n若目录内仍有接口、用例等资产，删除将被拒绝。'
    }
    await ElMessageBox.confirm(message, '提示', {
      type: 'warning',
      confirmButtonText: cascade ? '一并删除' : '确认',
      cancelButtonText: '取消'
    })
    await catalogApi.delete(data.id, cascade ? { cascade: true } : {})
    ElMessage.success('删除成功')
    await loadTree()
    emit('changed')
  } catch (error) {
    if (error !== 'cancel') {
      const detail = error.response?.data?.detail
      const msg = Array.isArray(detail)
        ? detail.map((d) => d.msg || d).join('；')
        : (detail || '删除失败')
      ElMessage.error(msg)
    }
  }
}

const saveCatalog = async () => {
  if (!dialog.form.name?.trim()) {
    ElMessage.warning('请输入目录名称')
    return
  }
  const projectId = Number(props.projectId)
  if (!projectId || projectId <= 0) {
    ElMessage.warning('请先选择有效项目')
    return
  }
  dialog.saving = true
  try {
    const payload = {
      name: dialog.form.name.trim(),
      project_id: projectId,
      parent_id: dialog.form.parent_id || null,
      sort: dialog.form.sort ?? 0,
      description: dialog.form.description || ''
    }
    if (dialog.isEdit) {
      await catalogApi.update(dialog.form.id, payload)
    } else {
      await catalogApi.create(payload)
    }
    ElMessage.success('保存成功')
    dialog.visible = false
    await loadTree()
    emit('changed')
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '保存失败')
  } finally {
    dialog.saving = false
  }
}

defineExpose({ loadTree, rawTree })
</script>

<style scoped lang="scss">
.catalog-tree {
  background: var(--el-bg-color);
  border-radius: 10px;
  border: 1px solid var(--el-border-color-lighter);
  padding: 14px;
  overflow: hidden;
  display: flex;
  flex-direction: column;

  &--fill {
    height: 100%;
    min-height: 0;
  }

  .tree-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 10px;
    padding-bottom: 10px;
    border-bottom: 1px solid var(--el-border-color-lighter);
    flex-shrink: 0;

    .tree-title {
      font-weight: 600;
      font-size: 14px;
    }
  }

  .tree-search {
    margin-bottom: 10px;
    flex-shrink: 0;
  }

  .catalog-tree-inner {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    background: transparent;

    :deep(.el-tree-node__content) {
      height: 36px;
      border-radius: 6px;
      margin-bottom: 2px;
    }

    :deep(.el-tree-node.is-current > .el-tree-node__content) {
      background: var(--el-color-primary-light-9);
      box-shadow: inset 3px 0 0 var(--el-color-primary);
    }

    :deep(.el-tree-node__content:hover) {
      background: var(--el-fill-color-light);
    }
  }

  .tree-node {
    display: flex;
    align-items: center;
    flex: 1;
    min-width: 0;
    padding-right: 4px;

    &.is-all-node .node-label {
      font-weight: 600;
    }

    .node-icon {
      margin-right: 6px;
      color: var(--el-color-primary);
      flex-shrink: 0;
      font-size: 15px;
    }

    .node-label {
      flex: 1;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-size: 13px;
    }

    .node-badge {
      flex-shrink: 0;
      margin-left: 6px;
      padding: 0 6px;
      height: 18px;
      line-height: 18px;
      font-size: 11px;
      border-radius: 9px;
      background: var(--el-color-primary-light-8);
      color: var(--el-color-primary);
      font-variant-numeric: tabular-nums;
    }

    .node-actions {
      display: none;
      flex-shrink: 0;
      margin-left: 4px;
    }

    &:hover .node-actions {
      display: flex;
    }
  }
}
</style>
