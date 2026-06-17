<template>
  <div class="overview-panel">
    <el-row :gutter="16">
      <el-col :xs="12" :sm="8" :md="4" v-for="card in statCards" :key="card.key">
        <div class="stat-card" @click="card.tab && $emit('navigate', card.tab)">
          <div class="stat-value">{{ card.value }}</div>
          <div class="stat-label">{{ card.label }}</div>
        </div>
      </el-col>
    </el-row>

    <el-descriptions :column="3" border size="small" class="meta-block">
      <el-descriptions-item label="文档">{{ req.file_name || '-' }}</el-descriptions-item>
      <el-descriptions-item label="字数">{{ req.text_length || 0 }}</el-descriptions-item>
      <el-descriptions-item label="章节">{{ req.section_count || 0 }}</el-descriptions-item>
      <el-descriptions-item label="图片">{{ req.image_count || 0 }} 张</el-descriptions-item>
      <el-descriptions-item label="测试点已确认">{{ overview.test_point_confirmed || 0 }} / {{ overview.test_point_total || 0 }}</el-descriptions-item>
      <el-descriptions-item label="最新方案">{{ overview.latest_scheme?.title || '暂无' }}</el-descriptions-item>
    </el-descriptions>

    <div class="quick-actions">
      <el-button type="primary" @click="$emit('navigate', 'document')">需求文档与配置</el-button>
      <el-button @click="$emit('navigate', 'points')">测试点列表</el-button>
      <el-button @click="$emit('navigate', 'schemes')">测试方案</el-button>
      <el-button @click="$emit('navigate', 'cases')">功能用例</el-button>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      style="margin-top: 16px;"
      title="推荐流程：上传/解析需求 → 生成并确认测试点 → 生成测试方案 → 从测试点或文档生成功能用例 → 复制到功能用例库。"
    />
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  req: { type: Object, required: true },
  overview: { type: Object, default: () => ({}) }
})

defineEmits(['navigate'])

const statCards = computed(() => [
  { key: 'points', label: '测试点', value: props.overview.test_point_total || 0, tab: 'points' },
  { key: 'confirmed', label: '已确认', value: props.overview.test_point_confirmed || 0, tab: 'points' },
  { key: 'schemes', label: '测试方案', value: props.overview.scheme_count || 0, tab: 'schemes' },
  { key: 'cases', label: '功能用例', value: props.overview.case_count || 0, tab: 'cases' },
  { key: 'sections', label: '章节', value: props.req.section_count || 0, tab: 'document' }
])
</script>

<style scoped>
.overview-panel {
  padding: 4px 0;
}
.stat-card {
  background: #f5f7fa;
  border-radius: 8px;
  padding: 16px;
  text-align: center;
  cursor: pointer;
  margin-bottom: 12px;
  transition: background 0.2s;
}
.stat-card:hover {
  background: #ecf5ff;
}
.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: #303133;
}
.stat-label {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}
.meta-block {
  margin: 12px 0 16px;
}
.quick-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
</style>
