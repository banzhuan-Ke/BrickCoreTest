<template>
  <PageCard class="docs-page-card">
    <template #title>
      <div class="docs-header">
        <span>📚 文档中心</span>
        <div class="docs-actions">
          <el-button v-if="canEdit" size="small" icon="FolderAdd" @click="openFolderEditor()">
            新增目录
          </el-button>
          <el-button v-if="canEdit" type="primary" size="small" icon="Plus" @click="openEditor()">
            发布文档
          </el-button>
          <el-button v-if="canEdit" size="small" icon="Setting" @click="openManage">
            管理文档
          </el-button>
        </div>
      </div>
    </template>
    <template #main>
      <div class="docs-layout">
        <aside class="docs-sidebar">
          <el-input v-model="filterText" placeholder="搜索文档" clearable prefix-icon="Search" class="filter-input" />
          <el-scrollbar class="tree-scroll">
            <el-tree
              ref="treeRef"
              :data="treeData"
              :props="{ label: 'title', children: 'children' }"
              node-key="nodeKey"
              highlight-current
              default-expand-all
              :filter-node-method="filterNode"
              @node-click="onNodeClick"
            >
              <template #default="{ data }">
                <span class="tree-node">
                  <el-icon v-if="data.doc_type === 'video'" class="node-icon"><VideoCamera /></el-icon>
                  <el-icon v-else-if="data.type === 'custom'" class="node-icon"><Document /></el-icon>
                  <el-icon v-else-if="data.type === 'group'" class="node-icon"><Folder /></el-icon>
                  <el-icon v-else class="node-icon"><Notebook /></el-icon>
                  <span class="node-title">{{ data.title }}</span>
                  <span v-if="canEdit && data.type !== 'group'" class="node-actions" @click.stop>
                    <el-button link type="primary" size="small" @click="openEditorFromNode(data)">编辑</el-button>
                    <el-button link type="danger" size="small" @click="removeFromNode(data)">删除</el-button>
                  </span>
                  <span v-else-if="canEdit && data.type === 'group' && !data.is_orphan_group" class="node-actions" @click.stop>
                    <el-button link type="primary" size="small" @click="openEditorFromNode(data)">编辑</el-button>
                    <el-button link type="danger" size="small" @click="removeFromNode(data)">删除</el-button>
                  </span>
                </span>
              </template>
            </el-tree>
          </el-scrollbar>
        </aside>

        <section class="docs-content" v-loading="loading">
          <template v-if="currentTitle">
            <div class="content-head">
              <h2 class="content-title">{{ currentTitle }}</h2>
              <div v-if="canEdit && currentDoc" class="content-actions">
                <el-button size="small" icon="Edit" @click="editCurrentDoc">编辑</el-button>
                <el-button size="small" type="danger" icon="Delete" @click="deleteCurrentDoc">删除</el-button>
              </div>
            </div>
            <DocsHtml v-if="viewMode === 'markdown'" :html="contentHtml" />
            <div v-else-if="viewMode === 'video'" class="video-wrap">
              <video v-if="mediaUrl" :src="mediaUrl" controls style="max-width: 100%; max-height: 70vh;" />
              <el-empty v-else description="视频地址无效" />
            </div>
            <div v-else-if="viewMode === 'file'" class="file-wrap">
              <el-link v-if="mediaUrl" :href="mediaUrl" target="_blank" type="primary" icon="Download">
                下载附件
              </el-link>
              <el-empty v-else description="附件不可用" />
            </div>
            <div v-else-if="viewMode === 'link'" class="link-wrap">
              <el-link :href="linkUrl" target="_blank" type="primary">{{ linkUrl }}</el-link>
            </div>
          </template>
          <el-empty v-else description="请从左侧选择文档" />
        </section>
      </div>
    </template>
  </PageCard>

  <!-- 新建/编辑 -->
  <el-dialog
    v-model="editorVisible"
    :title="editorDialogTitle"
    width="760px"
    destroy-on-close
  >
    <el-form :model="editorForm" label-width="100px">
      <el-form-item label="标题" required>
        <el-input v-model="editorForm.title" />
      </el-form-item>
      <el-form-item v-if="showParentSelect" label="所属目录">
        <el-select v-model="editorForm.parent_id" clearable placeholder="不选则归入「团队文档」" style="width: 100%;">
          <el-option v-for="folder in customFolders" :key="folder.id" :label="folder.title" :value="folder.id" />
        </el-select>
      </el-form-item>
      <el-form-item v-if="!editorForm.builtin_id && !editorForm.is_builtin_group && !editorForm.is_custom_group" label="类型">
        <el-radio-group v-model="editorForm.doc_type">
          <el-radio value="markdown">Markdown 文章</el-radio>
          <el-radio value="video">视频</el-radio>
          <el-radio value="file">附件</el-radio>
          <el-radio value="link">外部链接</el-radio>
        </el-radio-group>
      </el-form-item>

      <el-form-item v-if="showMarkdownEditor" label="正文">
        <el-input v-model="editorForm.content" type="textarea" :rows="14" placeholder="支持 Markdown 语法" />
      </el-form-item>

      <el-form-item v-if="editorForm.doc_type === 'video' || editorForm.doc_type === 'file'" label="上传文件">
        <el-upload
          :auto-upload="false"
          :show-file-list="false"
          :on-change="onFilePick"
          accept=".mp4,.webm,.mov,.pdf,.doc,.docx,.ppt,.pptx,.png,.jpg,.jpeg,.zip"
        >
          <el-button type="primary" :loading="uploading">选择文件上传</el-button>
        </el-upload>
        <div v-if="editorForm.file_key" class="upload-hint">已上传：{{ editorForm.file_key }}</div>
      </el-form-item>

      <el-form-item v-if="editorForm.doc_type === 'link'" label="链接">
        <el-input v-model="editorForm.link_url" placeholder="https://..." />
      </el-form-item>

      <el-form-item label="排序">
        <el-input-number v-model="editorForm.sort_order" :min="0" />
      </el-form-item>
      <el-form-item v-if="!editorForm.builtin_id && !editorForm.is_builtin_group && !editorForm.is_custom_group" label="发布">
        <el-switch v-model="editorForm.is_published" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="editorVisible = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="saveArticle">保存</el-button>
    </template>
  </el-dialog>

  <!-- 管理列表 -->
  <el-drawer v-model="manageVisible" title="文档管理" size="640px">
    <el-table :data="manageList" size="small" stripe>
      <el-table-column prop="title" label="标题" min-width="160" show-overflow-tooltip />
      <el-table-column label="来源" width="88">
        <template #default="{ row }">
          <el-tag v-if="row.type === 'builtin_group'" size="small" type="info">系统目录</el-tag>
          <el-tag v-else-if="row.type === 'custom_group'" size="small" type="warning">自定义目录</el-tag>
          <el-tag v-else-if="row.type === 'builtin'" size="small">系统文档</el-tag>
          <el-tag v-else size="small" type="success">团队</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="doc_type" label="类型" width="72" />
      <el-table-column label="状态" width="72">
        <template #default="{ row }">
          <el-tag v-if="row.is_hidden" size="small" type="danger">已隐藏</el-tag>
          <el-tag v-else size="small" type="success">显示</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="160" fixed="right">
        <template #default="{ row }">
          <el-button v-if="row.is_hidden" link type="success" size="small" @click="restoreItem(row)">恢复</el-button>
          <template v-else>
            <el-button link type="primary" size="small" @click="openEditor(row)">编辑</el-button>
            <el-button link type="danger" size="small" @click="removeArticle(row)">删除</el-button>
          </template>
        </template>
      </el-table-column>
    </el-table>
  </el-drawer>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { VideoCamera, Document, Notebook, Folder } from '@element-plus/icons-vue'
import PageCard from '@/components/PageCard.vue'
import DocsHtml from '@/components/DocsHtml.vue'
import { docsApi } from '@/api/modules/docs'
import { UserStore } from '@/stores/module/UserStore'

const userStore = UserStore()
const route = useRoute()
const canEdit = computed(() => userStore.hasPermission('docs:edit'))

const loading = ref(false)
const filterText = ref('')
const treeRef = ref(null)
const treeData = ref([])
const manageList = ref([])
const customFolders = ref([])

const editorDialogTitle = computed(() => {
  if (editorForm.is_custom_group) return editorForm.id ? '编辑目录' : '新增目录'
  if (editorForm.builtin_id) return editorForm.is_builtin_group ? '编辑目录' : '编辑内置文档'
  return editorForm.id ? '编辑文档' : '发布文档'
})

const showParentSelect = computed(() => {
  return !editorForm.builtin_id && !editorForm.is_builtin_group && !editorForm.is_custom_group
})

const currentTitle = ref('')
const currentDoc = ref(null)
const contentHtml = ref('')
const viewMode = ref('markdown')
const mediaUrl = ref('')
const linkUrl = ref('')

const editorVisible = ref(false)
const manageVisible = ref(false)
const saving = ref(false)
const uploading = ref(false)

const defaultEditor = () => ({
  id: null,
  builtin_id: '',
  is_builtin_group: false,
  is_custom_group: false,
  parent_id: null,
  title: '',
  doc_type: 'markdown',
  content: '',
  file_key: '',
  link_url: '',
  sort_order: 0,
  is_published: true
})
const editorForm = reactive(defaultEditor())

const showMarkdownEditor = computed(() => {
  if (editorForm.is_builtin_group || editorForm.is_custom_group) return false
  if (editorForm.builtin_id) return true
  return editorForm.doc_type === 'markdown'
})

const buildTree = (builtinTree, customTree) => {
  const builtinNodes = (builtinTree || []).map(group => ({
    ...group,
    nodeKey: group.id,
    children: (group.children || []).map(c => ({
      ...c,
      nodeKey: `builtin-${c.id}`,
      leaf: true
    }))
  }))
  const customNodes = (customTree || []).map(group => ({
    ...group,
    nodeKey: group.id,
    children: (group.children || []).map(c => ({
      ...c,
      nodeKey: `custom-${c.doc_id}`,
      leaf: true
    }))
  }))
  return [...builtinNodes, ...customNodes]
}

const loadCatalog = async () => {
  const res = await docsApi.getCatalog()
  if (res.data?.code !== 200) return
  const { builtin_tree, custom_tree, custom_folders } = res.data.data || {}
  customFolders.value = custom_folders || []
  treeData.value = buildTree(builtin_tree, custom_tree)
}

const loadManageList = async () => {
  const res = await docsApi.listManage()
  if (res.data?.code === 200) {
    manageList.value = res.data.data?.list || []
  }
}

const openManage = async () => {
  manageVisible.value = true
  await loadManageList()
}

const filterNode = (value, data) => {
  if (!value) return true
  return (data.title || '').toLowerCase().includes(value.toLowerCase())
}

watch(filterText, val => {
  treeRef.value?.filter(val)
})

const onNodeClick = async (data) => {
  if (data.type === 'group') return
  await loadDocNode(data)
}

const loadDocNode = async (data) => {
  loading.value = true
  currentTitle.value = data.title
  currentDoc.value = data
  try {
    if (data.type === 'builtin') {
      const res = await docsApi.getBuiltin(data.id)
      if (res.data?.code === 200) {
        const d = res.data.data
        currentTitle.value = d.title
        contentHtml.value = d.content_html || ''
        viewMode.value = 'markdown'
      }
    } else if (data.type === 'custom') {
      const res = await docsApi.getArticle(data.doc_id)
      if (res.data?.code === 200) {
        const d = res.data.data
        currentTitle.value = d.title
        viewMode.value = d.doc_type
        if (d.doc_type === 'markdown') {
          contentHtml.value = d.content_html || ''
        } else if (d.doc_type === 'link') {
          linkUrl.value = d.link_url || ''
        } else {
          mediaUrl.value = d.file_access_url || ''
        }
      }
    }
  } catch {
    ElMessage.error('加载文档失败')
  } finally {
    loading.value = false
  }
}

const openBuiltinById = async (docId) => {
  const findBuiltin = (nodes) => {
    for (const n of nodes || []) {
      if (n.type === 'builtin' && n.id === docId) return n
      const found = findBuiltin(n.children)
      if (found) return found
    }
    return null
  }
  const node = findBuiltin(treeData.value)
  if (node) {
    treeRef.value?.setCurrentKey(node.nodeKey)
    await loadDocNode(node)
  }
}

const fillEditorFromRow = async (row) => {
  Object.assign(editorForm, defaultEditor())
  if (row.type === 'custom_group') {
    Object.assign(editorForm, {
      id: row.doc_id || row.id,
      is_custom_group: true,
      doc_type: 'group',
      title: row.title,
      sort_order: row.sort_order || 0,
      is_published: true
    })
    return
  }
  if (row.type === 'builtin_group') {
    Object.assign(editorForm, {
      builtin_id: row.builtin_id,
      is_builtin_group: true,
      title: row.title,
      sort_order: row.sort_order || 0
    })
    return
  }
  if (row.type === 'builtin') {
    const res = await docsApi.getBuiltin(row.builtin_id)
    const d = res.data?.data || {}
    Object.assign(editorForm, {
      builtin_id: row.builtin_id,
      title: d.title || row.title,
      content: d.content_md || row.content || '',
      sort_order: row.sort_order || 0
    })
    return
  }
  let detail = row
  if (!row.content && row.doc_id) {
    try {
      const res = await docsApi.getArticle(row.doc_id)
      detail = res.data?.data || row
    } catch {
      detail = row
    }
  }
  Object.assign(editorForm, {
    id: detail.doc_id || detail.id,
    parent_id: detail.parent_id || null,
    title: detail.title,
    doc_type: detail.doc_type,
    content: detail.content || '',
    file_key: detail.file_key || '',
    link_url: detail.link_url || '',
    sort_order: detail.sort_order || 0,
    is_published: detail.is_published !== false
  })
}

const openFolderEditor = (row = null) => {
  if (row) {
    openEditor(row)
    return
  }
  Object.assign(editorForm, {
    ...defaultEditor(),
    is_custom_group: true,
    doc_type: 'group'
  })
  editorVisible.value = true
}

const openEditor = async (row = null) => {
  if (row) {
    loading.value = true
    try {
      await fillEditorFromRow(row)
    } catch {
      ElMessage.error('加载文档失败')
      return
    } finally {
      loading.value = false
    }
  } else {
    Object.assign(editorForm, defaultEditor())
  }
  editorVisible.value = true
}

const openEditorFromNode = async (data) => {
  if (data.is_custom_group) {
    await openEditor({
      type: 'custom_group',
      doc_id: data.group_id,
      title: data.title,
      sort_order: data.sort_order || 0
    })
    return
  }
  if (data.type === 'group') {
    await openEditor({
      type: 'builtin_group',
      builtin_id: data.id,
      title: data.title,
      sort_order: 0
    })
    return
  }
  if (data.type === 'builtin') {
    await openEditor({ type: 'builtin', builtin_id: data.id, title: data.title })
    return
  }
  await openEditor({ ...data, type: 'custom', doc_id: data.doc_id })
}

const editCurrentDoc = () => {
  if (!currentDoc.value) return
  openEditorFromNode(currentDoc.value)
}

const onFilePick = async (uploadFile) => {
  uploading.value = true
  try {
    const res = await docsApi.uploadFile(uploadFile.raw)
    if (res.data?.code === 200) {
      editorForm.file_key = res.data.data.file_key
      if (!editorForm.doc_type || editorForm.doc_type === 'markdown') {
        editorForm.doc_type = res.data.data.doc_type
      }
      ElMessage.success('上传成功')
    }
  } catch {
    ElMessage.error('上传失败')
  } finally {
    uploading.value = false
  }
}

const saveArticle = async () => {
  if (!editorForm.title?.trim()) {
    ElMessage.warning('请填写标题')
    return
  }
  saving.value = true
  try {
    if (editorForm.is_custom_group) {
      const payload = {
        title: editorForm.title,
        doc_type: 'group',
        sort_order: editorForm.sort_order,
        is_published: true
      }
      if (editorForm.id) {
        await docsApi.updateArticle(editorForm.id, payload)
      } else {
        await docsApi.createArticle(payload)
      }
    } else if (editorForm.builtin_id) {
      await docsApi.updateBuiltin(editorForm.builtin_id, {
        title: editorForm.title,
        content: editorForm.is_builtin_group ? null : editorForm.content,
        sort_order: editorForm.sort_order
      })
    } else {
      const payload = {
        title: editorForm.title,
        parent_id: editorForm.parent_id || null,
        doc_type: editorForm.doc_type,
        content: editorForm.content,
        file_key: editorForm.file_key || null,
        link_url: editorForm.link_url || null,
        sort_order: editorForm.sort_order,
        is_published: editorForm.is_published
      }
      if (editorForm.id) {
        await docsApi.updateArticle(editorForm.id, payload)
      } else {
        await docsApi.createArticle(payload)
      }
    }
    ElMessage.success('保存成功')
    editorVisible.value = false
    await loadCatalog()
    if (manageVisible.value) await loadManageList()
    if (currentDoc.value?.type === 'builtin' && currentDoc.value.id === editorForm.builtin_id) {
      await loadDocNode(currentDoc.value)
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

const removeItem = async (row) => {
  const name = row.title || '该文档'
  const isBuiltinGroup = row.type === 'builtin_group' || (row.type === 'group' && row.builtin_id)
  const isCustomGroup = row.type === 'custom_group' || row.is_custom_group
  const isGroup = isBuiltinGroup || isCustomGroup
  let tip = `删除「${name}」？`
  if (isBuiltinGroup) tip = `隐藏目录「${name}」及其下所有文档？`
  if (isCustomGroup) tip = `删除目录「${name}」？目录下的文档将一并删除。`
  await ElMessageBox.confirm(tip, '确认', { type: 'warning' })
  if (row.type === 'builtin' || row.type === 'builtin_group') {
    await docsApi.deleteBuiltin(row.builtin_id || row.id)
  } else {
    await docsApi.deleteArticle(row.doc_id || row.id)
  }
  ElMessage.success(isBuiltinGroup ? '已隐藏' : '已删除')
  if (isCurrentDoc(row)) {
    currentDoc.value = null
    currentTitle.value = ''
    contentHtml.value = ''
  }
  await loadCatalog()
  if (manageVisible.value) await loadManageList()
}

const isCurrentDoc = (row) => {
  if (!currentDoc.value) return false
  if (row.type === 'builtin' || row.type === 'builtin_group') {
    return currentDoc.value.id === (row.builtin_id || row.id)
  }
  return currentDoc.value.doc_id === (row.doc_id || row.id)
}

const removeArticle = (row) => removeItem(row)
const removeFromNode = (data) => {
  if (data.is_custom_group) {
    return removeItem({ type: 'custom_group', doc_id: data.group_id, title: data.title })
  }
  if (data.type === 'group') {
    return removeItem({ type: 'builtin_group', builtin_id: data.id, title: data.title })
  }
  if (data.type === 'builtin') {
    return removeItem({ type: 'builtin', builtin_id: data.id, title: data.title })
  }
  return removeItem({ ...data, type: 'custom' })
}

const deleteCurrentDoc = () => {
  if (!currentDoc.value) return
  removeFromNode(currentDoc.value)
}

const restoreItem = async (row) => {
  await docsApi.restoreBuiltin(row.builtin_id)
  ElMessage.success('已恢复显示')
  await loadCatalog()
  await loadManageList()
}

onMounted(async () => {
  await loadCatalog()
  const docId = route.query.doc
  if (docId && typeof docId === 'string') {
    await nextTick()
    await openBuiltinById(docId)
  }
})

watch(() => route.query.doc, async (docId) => {
  if (docId && typeof docId === 'string') {
    await openBuiltinById(docId)
  }
})
</script>

<style scoped>
.docs-page-card :deep(.main_box) {
  overflow: hidden;
  padding: 0;
  display: flex;
  flex-direction: column;
}
.docs-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}
.docs-actions { display: flex; gap: 8px; }
.docs-layout {
  flex: 1;
  min-height: 0;
  display: flex;
  gap: 16px;
  overflow: hidden;
  padding: 15px 20px;
}
.docs-sidebar {
  width: 300px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
  border-right: 1px solid #ebeef5;
  padding-right: 12px;
}
.filter-input { margin-bottom: 12px; flex-shrink: 0; }
.tree-scroll {
  flex: 1;
  min-height: 0;
}
.tree-scroll :deep(.el-scrollbar__wrap) {
  overflow-x: hidden;
}
.tree-node {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  width: 100%;
  padding-right: 4px;
}
.node-title { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; }
.node-icon { color: #909399; flex-shrink: 0; }
.node-actions {
  display: none;
  flex-shrink: 0;
  margin-left: auto;
}
.tree-node:hover .node-actions { display: inline-flex; gap: 2px; }
.docs-content {
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow-y: auto;
  padding: 0 8px 16px;
}
.content-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}
.content-title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
}
.content-actions { flex-shrink: 0; }
.video-wrap, .file-wrap, .link-wrap { padding: 16px 0; }
.upload-hint { font-size: 12px; color: #67c23a; margin-top: 8px; word-break: break-all; }
</style>
