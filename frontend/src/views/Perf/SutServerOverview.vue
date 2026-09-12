<template>
  <PageCard>
    <template #title>
      <div class="title-row">
        <el-button link type="primary" @click="$router.push('/perf-sut-servers')">← 列表</el-button>
        <div style="font-size: 18px; font-weight: bold;">被测服务器总览</div>
        <el-tag v-if="overview" size="small" type="success" style="margin-left: 8px">
          在线 {{ overview.online_count || 0 }} / {{ overview.total || 0 }}
        </el-tag>
        <el-button size="small" style="margin-left: auto" @click="load" :loading="loading">刷新</el-button>
      </div>
    </template>
    <template #main>
      <el-alert
        v-if="!proStore.projectInfo?.id"
        type="warning"
        :closable="false"
        show-icon
        style="margin-bottom: 14px"
      >请先在顶部选择项目</el-alert>
      <el-alert type="info" :closable="false" show-icon style="margin-bottom: 14px">
        近 15 分钟各机 CPU / 内存 / 磁盘摘要。点卡片进入<strong>监控详情</strong>（可筛选时间与指标类型，含网卡）。
        平台指标默认保留约 14 天。
      </el-alert>
      <el-empty v-if="!loading && !items.length" description="暂无被测服务器" />
      <div class="cards" v-loading="loading">
        <div
          v-for="row in items"
          :key="row.id"
          class="card"
          @click="$router.push(`/perf-sut-servers/${row.id}`)"
        >
          <div class="card-head">
            <strong>{{ row.name }}</strong>
            <el-tag size="small" :type="row.status === 'online' ? 'success' : 'info'">
              {{ row.status === 'online' ? '在线' : '离线' }}
            </el-tag>
          </div>
          <div class="meta">{{ row.hostname || '-' }} · {{ row.role || '无角色' }}</div>
          <div class="stats">
            <div>
              <div class="label">CPU 最新</div>
              <div class="val" :class="{ stale: isStale(row) }">{{ fmt(row.latest?.cpu_pct) }}%</div>
            </div>
            <div>
              <div class="label">内存 最新</div>
              <div class="val" :class="{ stale: isStale(row) }">{{ fmt(row.latest?.mem_pct) }}%</div>
            </div>
            <div>
              <div class="label">磁盘 最新</div>
              <div class="val" :class="{ stale: isStale(row) }">{{ fmt(row.latest?.disk_pct) }}%</div>
            </div>
            <div>
              <div class="label">15m CPU max</div>
              <div class="val">{{ fmt(row.summary_15m?.cpu_pct?.max) }}%</div>
            </div>
            <div>
              <div class="label">采样中</div>
              <div class="val">{{ row.sample_allowed ? '是' : '否' }}</div>
            </div>
          </div>
          <div class="sample-age" :class="{ stale: isStale(row) }">
            {{ latestAgeText(row) }}
          </div>
        </div>
      </div>
    </template>
  </PageCard>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import PageCard from '@/components/PageCard.vue'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { perfSutServerApi } from '@/api/modules/perf'

const proStore = ProjectStore()
const loading = ref(false)
const overview = ref(null)
const items = computed(() => overview.value?.data || [])

const STALE_MS = 5 * 60 * 1000
let loadSeq = 0

function fmt(v) {
  if (v == null || Number.isNaN(Number(v))) return '-'
  return Math.round(Number(v) * 10) / 10
}

function isStale(row) {
  const tsMs = row?.latest?.ts_ms
  if (tsMs == null) return true
  return Date.now() - Number(tsMs) > STALE_MS
}

function latestAgeText(row) {
  const tsMs = row?.latest?.ts_ms
  if (tsMs == null) return '暂无采样'
  const age = Date.now() - Number(tsMs)
  if (age < 0) return '采样时间异常'
  const sec = Math.floor(age / 1000)
  if (sec < 60) return `最近采样 ${sec}s 前`
  const min = Math.floor(sec / 60)
  if (min < 60) return `最近采样 ${min} 分钟前${min >= 5 ? '（可能过期）' : ''}`
  return `最近采样 ${Math.floor(min / 60)} 小时前（数据过期）`
}

async function load() {
  const pid = proStore.projectInfo?.id
  if (!pid) {
    overview.value = null
    return
  }
  const seq = ++loadSeq
  loading.value = true
  try {
    const res = await perfSutServerApi.getOverview({ project_id: pid })
    if (seq !== loadSeq) return
    overview.value = res?.data || res || null
  } catch (e) {
    if (seq !== loadSeq) return
    ElMessage.error(e?.data?.detail || e?.response?.data?.detail || '加载失败')
  } finally {
    if (seq === loadSeq) loading.value = false
  }
}

watch(() => proStore.projectInfo?.id, load, { immediate: true })
</script>

<style scoped>
.title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 14px;
}
.card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 14px;
  cursor: pointer;
  background: var(--el-fill-color-blank);
}
.card:hover {
  border-color: var(--el-color-primary-light-5);
}
.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}
.meta {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 12px;
}
.stats {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.label {
  font-size: 11px;
  color: var(--el-text-color-secondary);
}
.val {
  font-size: 16px;
  font-weight: 600;
}
.val.stale {
  color: var(--el-color-warning);
}
.sample-age {
  margin-top: 10px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.sample-age.stale {
  color: var(--el-color-warning);
}
</style>
