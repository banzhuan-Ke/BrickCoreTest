<template>
  <el-drawer
    :model-value="modelValue"
    :title="drawerTitle"
    size="600px"
    destroy-on-close
    class="req-preview-drawer"
    @close="emit('update:modelValue', false)"
  >
    <div v-loading="loading" class="drawer-body">
      <template v-if="preview">
        <div class="meta-row">
          <span class="lab">编号</span>
          <span class="val">{{ preview.requirement_key || '—' }}</span>
        </div>
        <div class="meta-row">
          <span class="lab">标题</span>
          <span class="val">{{ preview.title || preview.name || '—' }}</span>
        </div>
        <div class="meta-row" v-if="preview.source_type === 'ai' || aiRequirementId">
          <span class="lab">解析</span>
          <span class="val">{{ preview.parse_status || '—' }}</span>
        </div>
        <div class="meta-row" v-if="preview.review_status || preview.ai_review_status">
          <span class="lab">评审</span>
          <span class="val">{{ preview.review_status || preview.ai_review_status }}</span>
        </div>
        <div class="meta-row" v-if="preview.file_name">
          <span class="lab">文档</span>
          <span class="val">{{ preview.file_name }}</span>
        </div>
        <div class="meta-row" v-if="safeUrl(preview.url)">
          <span class="lab">外链</span>
          <a :href="safeUrl(preview.url)" target="_blank" rel="noopener noreferrer">{{ preview.url }}</a>
        </div>
        <div class="meta-row" v-if="preview.note">
          <span class="lab">备注</span>
          <span class="val pre">{{ preview.note }}</span>
        </div>

        <el-alert
          v-if="impactBanner"
          type="warning"
          :closable="false"
          show-icon
          class="impact-banner"
        >
          <template #title>需求文档已更新，关联用例可能已过期</template>
          <p class="impact-actions">
            建议重新发起需求评审或核对测试覆盖。
            <el-button
              v-if="showStartReview"
              link
              type="primary"
              @click="emit('start-review', aiRequirementId)"
            >发起需求评审</el-button>
          </p>
        </el-alert>

        <div v-if="sectionTree.length" class="sections-block">
          <div class="section-title">章节（{{ preview.section_count || sectionTree.length }}）</div>
          <el-tree
            :data="sectionTree"
            node-key="id"
            default-expand-all
            highlight-current
            :props="{ label: 'label', children: 'children' }"
            @node-click="onSectionClick"
          />
          <div v-if="selectedExcerpt" class="section-excerpt">
            <div class="excerpt-label">{{ selectedSectionTitle }}</div>
            <div class="excerpt-text">{{ selectedExcerpt }}</div>
          </div>
        </div>

        <el-collapse v-if="preview.original_content" v-model="contentCollapse" class="content-collapse">
          <el-collapse-item title="需求正文" name="body">
            <div ref="contentRef" class="content-text">{{ preview.original_content }}</div>
            <p v-if="preview.text_length > 5000" class="trunc-hint">
              正文已截断展示，完整内容请在工作台查看。
            </p>
          </el-collapse-item>
        </el-collapse>
        <div v-else-if="preview.source_type === 'external' && !preview.note" class="empty-hint">
          外部需求暂无正文，可填写备注或升级为项目需求后上传文档。
        </div>
      </template>
      <el-empty v-else-if="!loading" description="无法加载需求预览" />
    </div>
    <template #footer v-if="showActions">
      <div class="drawer-footer">
        <router-link
          v-if="aiRequirementId"
          :to="`/ai-testing/requirements/${aiRequirementId}`"
          class="link-btn"
        >
          打开需求工作台
        </router-link>
        <el-button @click="emit('update:modelValue', false)">关闭</el-button>
        <el-button v-if="canEdit" type="primary" plain @click="emit('edit')">编辑备注/链接</el-button>
        <el-button v-if="canEdit && canReplaceDoc" type="primary" @click="emit('replace-doc')">
          更新文档
        </el-button>
        <el-button v-if="canEdit && canUpgrade" type="success" plain @click="emit('upgrade')">
          升级为项目需求
        </el-button>
      </div>
    </template>
  </el-drawer>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { testReleaseApi } from '@/api/testManagement'
import { aiRequirementApi } from '@/api/modules/ai.js'
import { excerptAroundContent } from '@/utils/releaseRequirement.js'

const props = defineProps({
  modelValue: Boolean,
  releaseReq: { type: Object, default: null },
  aiRequirementId: { type: Number, default: null },
  projectId: { type: Number, required: true },
  releaseId: { type: Number, default: null },
  showActions: { type: Boolean, default: true },
  canEdit: { type: Boolean, default: false },
  impactBanner: { type: Boolean, default: false },
  showStartReview: { type: Boolean, default: false },
  previewData: { type: Object, default: null }
})

const emit = defineEmits(['update:modelValue', 'edit', 'replace-doc', 'upgrade', 'start-review'])

const loading = ref(false)
const preview = ref(null)
const contentCollapse = ref(['body'])
const selectedExcerpt = ref('')
const selectedSectionTitle = ref('')
const contentRef = ref(null)

const aiRequirementId = computed(() => {
  if (props.aiRequirementId) return props.aiRequirementId
  const row = props.releaseReq
  if (row?.ai_requirement_id) return row.ai_requirement_id
  const m = String(row?.requirement_key || '').match(/^REQ-(\d+)$/i)
  return m ? Number(m[1]) : null
})

const canReplaceDoc = computed(() => props.releaseReq?.source_type === 'ai' || !!aiRequirementId.value)
const canUpgrade = computed(
  () => props.releaseReq && props.releaseReq.source_type !== 'ai' && !aiRequirementId.value
)

const drawerTitle = computed(() => {
  const t = preview.value?.title || preview.value?.name || props.releaseReq?.title
  return t ? `需求预览 · ${t}` : '需求预览'
})

const sectionTree = computed(() => {
  const sections = preview.value?.sections || []
  if (!sections.length) return []
  const byParent = new Map()
  for (const s of sections) {
    const pid = s.parent_id ?? s.parentId ?? '__root__'
    if (!byParent.has(pid)) byParent.set(pid, [])
    byParent.get(pid).push(s)
  }
  const build = (parentKey) =>
    (byParent.get(parentKey) || []).map((s) => ({
      id: s.id || s.title,
      label: s.title || s.id || '—',
      raw: s,
      children: build(s.id)
    }))
  const roots = build('__root__')
  if (roots.length) return roots
  return sections.slice(0, 80).map((s) => ({
    id: s.id || s.title,
    label: s.title || s.id || '—',
    raw: s
  }))
})

const safeUrl = (url) => {
  const u = String(url || '').trim()
  if (!u) return null
  const lower = u.toLowerCase()
  if (lower.startsWith('http://') || lower.startsWith('https://')) return u
  return null
}

const onSectionClick = (node) => {
  const title = node.label || ''
  selectedSectionTitle.value = title
  selectedExcerpt.value = excerptAroundContent(preview.value?.original_content, title)
}

const load = async () => {
  selectedExcerpt.value = ''
  selectedSectionTitle.value = ''
  if (props.previewData) {
    preview.value = props.previewData
    return
  }
  if (props.releaseReq && props.releaseId) {
    loading.value = true
    try {
      const res = await testReleaseApi.getRequirementPreview(
        props.releaseId,
        props.releaseReq.id,
        props.projectId
      )
      preview.value = res.data?.data || null
    } catch {
      preview.value = null
    } finally {
      loading.value = false
    }
    return
  }
  if (aiRequirementId.value && props.projectId) {
    loading.value = true
    try {
      const res = await aiRequirementApi.getDetail(aiRequirementId.value, props.projectId)
      const d = res.data?.data || {}
      preview.value = {
        requirement_key: `REQ-${d.id}`,
        name: d.name,
        source_type: 'ai',
        ai_requirement_id: d.id,
        original_content: d.original_content || '',
        sections: d.sections || [],
        file_name: d.file_name,
        review_status: d.review_status,
        parse_status: d.parse_status,
        section_count: d.section_count,
        text_length: d.text_length
      }
    } catch {
      preview.value = null
    } finally {
      loading.value = false
    }
    return
  }
  preview.value = null
}

watch(
  () => [props.modelValue, props.releaseReq, props.previewData, props.aiRequirementId],
  (v) => {
    if (v[0]) load()
  }
)
</script>

<style scoped>
.drawer-body {
  min-height: 120px;
}
.meta-row {
  display: flex;
  gap: 10px;
  margin-bottom: 10px;
  font-size: 13px;
  line-height: 1.5;
}
.meta-row .lab {
  flex: 0 0 48px;
  color: #909399;
}
.meta-row .val {
  flex: 1;
  color: #303133;
}
.meta-row .pre {
  white-space: pre-wrap;
}
.section-title {
  font-size: 13px;
  font-weight: 600;
  color: #344054;
  margin: 14px 0 8px;
}
.content-collapse {
  margin-top: 12px;
  border: none;
}
.content-collapse :deep(.el-collapse-item__header) {
  font-weight: 600;
  font-size: 13px;
}
.content-text {
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  padding: 12px;
  background: #f9fafb;
  border: 1px solid #eaecf0;
  border-radius: 8px;
  max-height: 360px;
  overflow: auto;
}
.section-excerpt {
  margin-top: 10px;
  padding: 10px 12px;
  background: #fff;
  border: 1px dashed #dcdfe6;
  border-radius: 8px;
}
.excerpt-label {
  font-size: 12px;
  color: #909399;
  margin-bottom: 6px;
}
.excerpt-text {
  font-size: 13px;
  line-height: 1.55;
  white-space: pre-wrap;
  max-height: 200px;
  overflow: auto;
}
.trunc-hint {
  margin: 8px 0 0;
  font-size: 12px;
  color: #909399;
}
.empty-hint {
  color: #909399;
  font-size: 13px;
  margin-top: 12px;
}
.impact-banner {
  margin: 12px 0;
}
.impact-actions {
  margin: 4px 0 0;
  font-size: 13px;
}
.drawer-footer {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
  align-items: center;
}
.link-btn {
  margin-right: auto;
  color: var(--el-color-primary);
  text-decoration: none;
  font-size: 13px;
}
</style>
