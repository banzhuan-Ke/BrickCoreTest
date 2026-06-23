<template>
  <div 
    class="suite-case-list"
    @dragover.prevent
    @drop="handleDrop"
  >
    <div class="case-list">
      <div 
        v-for="(element, index) in suiteCaseList" 
        :key="element.id || element.cases_id"
        class="case-item"
        draggable="true"
        @dragstart="handleDragStart($event, index)"
        @dragover.prevent
        @drop="handleItemDrop($event, index)"
      >
        <div class="drag-handle">
          <el-icon><Rank /></el-icon>
        </div>
        <div class="case-info">
          <span class="case-index">{{ index + 1 }}</span>
          <span class="case-name" :title="element.cases_name || element.name">{{ element.cases_name || element.name }}</span>
        </div>
        <div class="case-actions">
          <el-select
            v-model="element.run_mode"
            size="small"
            class="run-mode-select"
            @click.stop
          >
            <el-option label="链路" value="chain" />
            <el-option label="独立" value="standalone" />
          </el-select>
          <el-tooltip content="跳过执行" placement="top">
            <el-switch 
              v-model="element.skip" 
              size="small"
              @click.stop
            />
          </el-tooltip>
          <el-tooltip content="编辑用例" placement="top">
            <el-button 
              @click="editCase(element.cases_id || element.id)" 
              :icon="Edit" 
              circle 
              size="small"
              type="primary" 
              plain
            />
          </el-tooltip>
          <el-tooltip content="移除" placement="top">
            <el-button 
              @click="removeCase(index)" 
              :icon="Delete" 
              circle 
              size="small"
              type="danger" 
              plain
            />
          </el-tooltip>
        </div>
      </div>
    </div>
    
    <div v-if="suiteCaseList.length === 0" class="empty-tip">
      <el-empty description="暂无套件用例，请从下方拖拽添加" :image-size="60" />
    </div>
    <p v-else class="run-mode-hint">
      链路：参与变量传递，上游失败时跳过后续链路用例；独立：每次独立随机，失败不影响其他用例。
    </p>
  </div>
</template>

<script setup>
import { ref, onMounted, watch, defineExpose } from 'vue'
import { useRouter } from 'vue-router'
import { Rank, Edit, Delete } from '@element-plus/icons-vue'
import http from '@/api/index'
import { ElMessage } from 'element-plus'

const props = defineProps({
  suiteId: {
    type: [String, Number],
    required: true
  },
  defaultRunMode: {
    type: String,
    default: 'standalone'
  }
})

const router = useRouter()
const suiteCaseList = ref([])
const originalCases = ref([])

const emit = defineEmits(['cases-change'])

const getSuiteCases = async () => {
  if (!props.suiteId) return
  try {
    const res = await http.suiteApi.getSuiteCaseList(props.suiteId)
    if (res.status === 200) {
      suiteCaseList.value = (res.data || []).map((item) => ({
        ...item,
        run_mode: item.run_mode || 'standalone',
      }))
      originalCases.value = JSON.parse(JSON.stringify(suiteCaseList.value))
    }
  } catch (error) {
    console.error('获取套件用例失败:', error)
  }
}

watch(() => props.suiteId, (newId) => {
  if (newId) {
    getSuiteCases()
  }
}, { immediate: true })

watch(
  suiteCaseList,
  (list) => {
    const ids = list
      .map((item) => item.cases_id || item.id)
      .filter((id) => id != null && id !== '')
    emit('cases-change', ids)
  },
  { deep: true, immediate: true }
)

const removeCase = async (index) => {
  suiteCaseList.value.splice(index, 1)
  suiteCaseList.value.forEach((item, idx) => {
    item.sort = idx + 1
  })
  ElMessage.success('移除成功')
}

const editCase = (caseId) => {
  router.push({ name: 'editCase', params: { id: caseId } })
}

const handleSort = () => {
  suiteCaseList.value.forEach((item, index) => {
    item.sort = index + 1
  })
}

const dragIndex = ref(-1)

const handleDragStart = (e, index) => {
  dragIndex.value = index
  e.dataTransfer.effectAllowed = 'move'
}

const handleItemDrop = (e, dropIndex) => {
  e.preventDefault()
  if (dragIndex.value === -1 || dragIndex.value === dropIndex) return
  
  const item = suiteCaseList.value.splice(dragIndex.value, 1)[0]
  suiteCaseList.value.splice(dropIndex, 0, item)
  
  handleSort()
  
  dragIndex.value = -1
}

const handleDrop = (e) => {
  e.preventDefault()
  const data = e.dataTransfer.getData('application/json')
  if (!data) {
    return
  }
  
  try {
    const caseItem = JSON.parse(data)
    
    const exists = suiteCaseList.value.some(item => 
      (item.cases_id === caseItem.id) || (item.id === caseItem.id)
    )
    if (exists) {
      ElMessage.warning('该用例已在套件中')
      return
    }
    
    const newItem = {
      id: Date.now(),
      cases_id: caseItem.id,
      cases_name: caseItem.name,
      suite_id: props.suiteId,
      sort: suiteCaseList.value.length + 1,
      skip: false,
      run_mode: props.defaultRunMode || 'standalone',
      isNew: true
    }
    suiteCaseList.value.push(newItem)
    
    ElMessage.success('添加用例成功，请保存套件')
  } catch (error) {
    console.error('添加用例失败:', error)
    ElMessage.error('添加用例失败')
  }
}

const getCurrentCases = () => {
  return suiteCaseList.value
}

const saveSuiteCases = async () => {
  try {
    const currentIds = suiteCaseList.value
      .filter(item => !item.isNew && item.cases_id)
      .map(item => item.cases_id)
    
    for (const original of originalCases.value) {
      if (!currentIds.includes(original.cases_id)) {
        await http.suiteApi.deleteCase(props.suiteId, original.id)
      }
    }
    
    const newCases = suiteCaseList.value.filter(item => item.isNew)
    for (const item of newCases) {
      await http.suiteApi.addCase(props.suiteId, {
        cases_id: item.cases_id,
        sort: item.sort
      })
    }
    
    const sortData = suiteCaseList.value.map((item, index) => ({
      cases_id: item.cases_id,
      sort: index + 1,
      skip: !!item.skip,
      run_mode: item.run_mode || 'standalone',
    }))
    await http.suiteApi.updateCaseOrder(props.suiteId, { case_orders: sortData })
    
    await getSuiteCases()
    return true
  } catch (error) {
    console.error('保存套件用例失败:', error)
    ElMessage.error('保存套件用例失败')
    return false
  }
}

defineExpose({
  getCurrentCases,
  saveSuiteCases
})

onMounted(() => {
  getSuiteCases()
})
</script>

<style scoped lang="scss">
.suite-case-list {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  min-height: 100px;
}

.case-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.case-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  transition: all 0.2s;
  
  &:hover {
    border-color: var(--el-color-primary);
    background: var(--el-color-primary-light-9);
  }
}

.drag-handle {
  cursor: grab;
  color: var(--el-text-color-secondary);
  padding: 4px;
  
  &:active {
    cursor: grabbing;
  }
}

.case-info {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  overflow: hidden;
  min-width: 0;
}

.case-index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  background: var(--el-color-primary);
  color: white;
  border-radius: 50%;
  font-size: 11px;
  font-weight: bold;
  flex-shrink: 0;
}

.case-name {
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.case-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.run-mode-select {
  width: 72px;
}

.empty-tip {
  padding: 20px;
}

.run-mode-hint {
  margin: 10px 0 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}

.ghost {
  opacity: 0.5;
  background: var(--el-color-primary-light-9);
  border: 2px dashed var(--el-color-primary);
}

.chosen {
  border: 2px solid var(--el-color-primary);
}

.dragging {
  transform: scale(1.02);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}
</style>
