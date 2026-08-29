<template>
  <div class="notification-center">
    <div class="toolbar">
      <h2>通知中心</h2>
      <div class="toolbar-actions">
        <el-radio-group v-model="tab" size="small" @change="onTabChange">
          <el-radio-button value="unread">未读</el-radio-button>
          <el-radio-button value="all">全部</el-radio-button>
        </el-radio-group>
        <el-button
          v-if="unreadCount > 0"
          type="primary"
          plain
          size="small"
          @click="markAllRead"
        >全部已读</el-button>
        <el-button size="small" @click="load">刷新</el-button>
        <el-button link type="primary" size="small" @click="router.push({ path: '/profile', query: { tab: 'notify' } })">
          通知偏好
        </el-button>
        <el-button link type="primary" size="small" @click="router.push('/system/notification-log')">
          推送记录
        </el-button>
      </div>
    </div>

    <el-table v-loading="loading" :data="items" border stripe @row-click="openItem">
      <el-table-column prop="title" label="标题" min-width="240" show-overflow-tooltip />
      <el-table-column prop="body" label="摘要" min-width="200" show-overflow-tooltip />
      <el-table-column prop="project_name" label="项目" width="140" show-overflow-tooltip />
      <el-table-column label="外发" width="200">
        <template #default="{ row }">
          <div class="dispatch-tags">
            <template v-if="row.external_dispatch?.pending">
              <el-tag size="small" type="info">外发排队中</el-tag>
            </template>
            <template v-else-if="(row.external_dispatch?.channels || []).length">
              <el-tooltip
                v-for="ch in row.external_dispatch.channels"
                :key="`${row.id}-${ch.channel}`"
                :content="ch.error || ''"
                :disabled="!ch.error"
              >
                <el-tag size="small" :type="dispatchTagType(ch.status)" class="dispatch-tag">
                  {{ dispatchChannelLabel(ch.channel) }}·{{ dispatchStatusLabel(ch.status) }}
                </el-tag>
              </el-tooltip>
            </template>
            <span v-else class="muted">仅站内信</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="80">
        <template #default="{ row }">
          <el-tag :type="row.is_read ? 'info' : 'warning'" size="small">
            {{ row.is_read ? '已读' : '未读' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="时间" width="160">
        <template #default="{ row }">{{ formatTime(row.create_time) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="100" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click.stop="openItem(row)">打开</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="pager">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="size"
        :total="total"
        layout="total, prev, pager, next, sizes"
        :page-sizes="[20, 50, 100]"
        @current-change="load"
        @size-change="onSizeChange"
      />
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import http from '@/api/index'
import { inboxApi } from '@/api/modules/sys'
import { ProjectStore } from '@/stores/module/ProjectStore'

const router = useRouter()
const proStore = ProjectStore()

const tab = ref('unread')
const items = ref([])
const loading = ref(false)
const unreadCount = ref(0)
const page = ref(1)
const size = ref(20)
const total = ref(0)

const formatTime = (v) => (v ? String(v).replace('T', ' ').slice(0, 16) : '')

const dispatchChannelLabel = (ch) => {
  const map = { email: '邮件', dingtalk: '钉钉', wechat: '企微', feishu: '飞书' }
  return map[ch] || ch
}

const dispatchStatusLabel = (st) => {
  const map = { success: '成功', failed: '失败', skipped: '跳过', unknown: '未知' }
  return map[st] || st
}

const dispatchTagType = (st) => {
  if (st === 'success') return 'success'
  if (st === 'skipped') return 'info'
  return 'danger'
}

const loadUnreadCount = async () => {
  try {
    const res = await inboxApi.unreadCount()
    unreadCount.value = res.data?.data?.count || 0
  } catch {
    unreadCount.value = 0
  }
}

const load = async () => {
  loading.value = true
  try {
    const res = await inboxApi.list({
      unread_only: tab.value === 'unread',
      page: page.value,
      size: size.value
    })
    const data = res.data?.data || {}
    items.value = data.data || []
    total.value = data.total || 0
  } catch {
    items.value = []
    total.value = 0
  } finally {
    loading.value = false
    await loadUnreadCount()
  }
}

const onTabChange = () => {
  page.value = 1
  load()
}

const onSizeChange = () => {
  page.value = 1
  load()
}

const markAllRead = async () => {
  await inboxApi.markAllRead()
  await load()
}

const openItem = async (item) => {
  if (!item.is_read) {
    try {
      await inboxApi.markRead(item.id)
      item.is_read = true
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
      /* ignore */
    }
  }
  const query = { ...(item.link_query || {}) }
  if (item.link_path) {
    router.push({ path: item.link_path, query })
  }
}

onMounted(load)
</script>

<style scoped>
.notification-center {
  padding: 16px 20px;
}
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  gap: 12px;
}
.toolbar h2 {
  margin: 0;
  font-size: 18px;
}
.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}
.pager {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
.dispatch-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
}
.dispatch-tag {
  margin: 0;
}
.muted {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
</style>
