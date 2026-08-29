<template>
  <div class="notification-inbox">
    <div class="inbox-toolbar">
      <el-radio-group v-model="tab" size="small" @change="loadList">
        <el-radio-button value="unread">未读</el-radio-button>
        <el-radio-button value="all">全部</el-radio-button>
      </el-radio-group>
      <el-button
        v-if="unreadCount > 0"
        link
        type="primary"
        size="small"
        @click="markAllRead"
      >全部已读</el-button>
    </div>
    <div v-loading="loading" class="inbox-list">
      <div
        v-for="item in items"
        :key="item.id"
        class="inbox-item"
        :class="{ unread: !item.is_read }"
        @click="openItem(item)"
      >
        <div class="inbox-item-dot" v-if="!item.is_read" />
        <div class="inbox-item-main">
          <div class="inbox-item-title">{{ item.title }}</div>
          <div v-if="item.body" class="inbox-item-body">{{ item.body }}</div>
          <div v-if="dispatchTags(item).length" class="inbox-dispatch">
            <el-tag
              v-for="tag in dispatchTags(item)"
              :key="`${item.id}-${tag.label}`"
              size="small"
              :type="tag.type"
            >{{ tag.label }}</el-tag>
          </div>
          <div class="inbox-item-meta">
            <span class="inbox-cat">{{ categoryLabel(item.category) }}</span>
            <span v-if="item.project_name" class="inbox-proj">{{ item.project_name }}</span>
            <span class="inbox-time">{{ formatTime(item.create_time) }}</span>
          </div>
        </div>
      </div>
      <el-empty v-if="!loading && !items.length" :description="tab === 'unread' ? '暂无未读通知' : '暂无通知'" />
    </div>
    <div class="inbox-footer">
      <el-button link type="primary" size="small" @click="goCenter">查看全部</el-button>
      <span class="inbox-footer-hint">下拉最多 15 条</span>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import http from '@/api/index'
import { inboxApi } from '@/api/modules/sys'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { notificationCategoryLabel } from '@/utils/notificationLabels'

const emit = defineEmits(['read', 'refresh-count'])

const router = useRouter()
const proStore = ProjectStore()

const tab = ref('unread')
const items = ref([])
const loading = ref(false)
const unreadCount = ref(0)

const formatTime = (v) => (v ? String(v).replace('T', ' ').slice(0, 16) : '')
const categoryLabel = notificationCategoryLabel

const channelLabel = (ch) => {
  const map = { email: '邮件', dingtalk: '钉钉', wechat: '企微', feishu: '飞书' }
  return map[ch] || ch
}

const statusLabel = (st) => {
  const map = { success: '成功', failed: '失败', skipped: '跳过' }
  return map[st] || st
}

const dispatchTagType = (st) => {
  if (st === 'success') return 'success'
  if (st === 'skipped') return 'info'
  return 'danger'
}

const dispatchTags = (item) => {
  const d = item.external_dispatch
  if (!d) return []
  if (d.pending) return [{ label: '外发排队中', type: 'info' }]
  return (d.channels || []).map((ch) => ({
    label: `${channelLabel(ch.channel)}·${statusLabel(ch.status)}`,
    type: dispatchTagType(ch.status)
  }))
}

const loadUnreadCount = async () => {
  try {
    const res = await inboxApi.unreadCount()
    unreadCount.value = res.data?.data?.count || 0
    emit('refresh-count', unreadCount.value)
  } catch {
    unreadCount.value = 0
    emit('refresh-count', 0)
  }
}

const loadList = async () => {
  loading.value = true
  try {
    const res = await inboxApi.list({
      unread_only: tab.value === 'unread',
      size: 15
    })
    items.value = res.data?.data?.data || []
  } catch {
    items.value = []
  } finally {
    loading.value = false
  }
}

const markAllRead = async () => {
  await inboxApi.markAllRead()
  await loadUnreadCount()
  await loadList()
}

const goCenter = () => {
  router.push({ path: '/notifications' })
}

const openItem = async (item) => {
  if (!item.is_read) {
    try {
      await inboxApi.markRead(item.id)
      item.is_read = true
      emit('read', item)
      await loadUnreadCount()
    } catch {
      /* ignore */
    }
  }
  if (item.project_id && item.project_id !== proStore.projectInfo?.id) {
    try {
      const res = await http.projectApi.getProjectDetail(item.project_id)
      const data = res.data?.data ?? res.data
      if (data?.id) await proStore.applyProject(data)
    } catch {
      /* 忽略项目切换失败 */
    }
  }
  const query = { ...(item.link_query || {}) }
  if (item.link_path) {
    router.push({ path: item.link_path, query })
  }
}

const refresh = async () => {
  await Promise.all([loadUnreadCount(), loadList()])
}

onMounted(refresh)

defineExpose({ refresh, loadUnreadCount })
</script>

<style scoped>
.notification-inbox {
  width: 380px;
  max-height: 440px;
  display: flex;
  flex-direction: column;
  border-radius: 14px;
  overflow: hidden;
  background: #fff;
}
.inbox-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px 10px;
  background: linear-gradient(180deg, #f8fafc 0%, #fff 100%);
  border-bottom: 1px solid #eef2f6;
}
.inbox-list {
  overflow-y: auto;
  max-height: 360px;
  padding: 8px 10px;
}
.inbox-item {
  position: relative;
  display: flex;
  gap: 10px;
  padding: 12px 12px 12px 14px;
  margin-bottom: 8px;
  cursor: pointer;
  border-radius: 12px;
  border: 1px solid #eef2f6;
  background: #fff;
  box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
  transition: background 0.15s, border-color 0.15s, box-shadow 0.15s;
}
.inbox-item:hover {
  background: #f8fbff;
  border-color: #d6e4ff;
  box-shadow: 0 4px 12px rgba(64, 158, 255, 0.08);
}
.inbox-item.unread {
  background: linear-gradient(135deg, #f0f7ff 0%, #f8fbff 100%);
  border-color: #cfe0ff;
}
.inbox-item-dot {
  position: absolute;
  left: 6px;
  top: 18px;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #409eff;
}
.inbox-item-main { flex: 1; min-width: 0; }
.inbox-item-title {
  font-size: 13px;
  font-weight: 600;
  line-height: 1.45;
  margin-bottom: 4px;
  color: #1f2937;
}
.inbox-item-body {
  font-size: 12px;
  color: #6b7280;
  line-height: 1.45;
  margin-bottom: 6px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.inbox-dispatch {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 6px;
}
.inbox-item-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 11px;
  color: #9ca3af;
}
.inbox-cat {
  padding: 1px 8px;
  border-radius: 999px;
  background: #f3f4f6;
  color: #6b7280;
}
.inbox-proj { max-width: 100px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.inbox-footer {
  padding: 10px 14px 12px;
  border-top: 1px solid #eef2f6;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  background: #fafbfc;
}
.inbox-footer-hint {
  font-size: 11px;
  color: #c0c4cc;
}
</style>
