<template>
  <div class="condition-edit">
    <div class="condition-header">
      <el-icon size="20" color="#e6a23c"><Share /></el-icon>
      <span class="title">条件分支配置</span>
      <el-text type="info" size="small">按顺序匹配第一个满足条件的分支</el-text>
    </div>

    <!-- 分支列表 -->
    <div class="branches-list">
      <div
        v-for="(branch, index) in localBranches"
        :key="branch.id || `branch_${index}`"
        class="branch-card"
        :class="{ 'is-else': branch.condition?.type === 'else' }"
      >
        <!-- 分支头部 -->
        <div class="branch-card-header">
          <div class="branch-title">
            <el-tag :type="branch.condition?.type === 'else' ? 'info' : 'primary'" effect="dark" size="small">
              {{ branch.condition?.type === 'else' ? 'ELSE' : `IF ${index + 1}` }}
            </el-tag>
            <el-input
              v-model="branch.name"
              size="small"
              placeholder="分支名称"
              class="branch-name-input"
              @change="updateBranches"
            />
          </div>
          <div class="branch-actions" v-if="branch.condition?.type !== 'else'">
            <el-button
              link
              type="danger"
              size="small"
              :icon="Delete"
              @click="removeBranch(index)"
            >
              删除
            </el-button>
          </div>
        </div>

        <!-- 条件配置 -->
        <div v-if="branch.condition?.type !== 'else'" class="condition-config">
          <el-form label-width="80px" size="small">
            <el-form-item label="条件类型">
              <el-select v-model="branch.condition.type" placeholder="选择条件类型" style="width: 100%" @change="updateBranches">
                <el-option
                  v-for="item in conditionTypes"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </el-select>
            </el-form-item>

            <!-- 元素相关条件 -->
            <template v-if="isElementCondition(branch.condition.type)">
              <el-form-item label="元素定位">
                <el-input
                  v-model="branch.condition.locator"
                  placeholder="如: #username 或 xpath=//input"
                  @change="updateBranches"
                />
              </el-form-item>
            </template>

            <!-- 文本对比条件 -->
            <template v-if="isTextCompareCondition(branch.condition.type)">
              <el-form-item label="预期值">
                <el-input
                  v-model="branch.condition.expected_value"
                  placeholder="请输入预期文本"
                  @change="updateBranches"
                />
              </el-form-item>
            </template>

            <!-- 页面标题条件 -->
            <template v-if="branch.condition.type === 'page_title_equals'">
              <el-form-item label="预期标题">
                <el-input
                  v-model="branch.condition.expected_value"
                  placeholder="请输入预期页面标题"
                />
              </el-form-item>
            </template>

            <!-- 页面URL条件 -->
            <template v-if="branch.condition.type === 'page_url_contains'">
              <el-form-item label="URL包含">
                <el-input
                  v-model="branch.condition.expected_value"
                  placeholder="请输入URL包含的文本"
                />
              </el-form-item>
            </template>

            <!-- JS表达式条件 -->
            <template v-if="branch.condition.type === 'custom_js'">
              <el-form-item label="JS表达式">
                <el-input
                  v-model="branch.condition.script"
                  type="textarea"
                  :rows="3"
                  placeholder="返回 true/false 的JavaScript表达式，如: document.title.includes('首页')"
                />
              </el-form-item>
            </template>

            <el-form-item label="判断方式">
              <el-radio-group v-model="branch.condition.operator" @change="updateBranches">
                <el-radio label="is_true">条件为真</el-radio>
                <el-radio label="is_false">条件为假</el-radio>
              </el-radio-group>
            </el-form-item>
          </el-form>
        </div>

        <!-- ELSE分支说明 -->
        <div v-else-if="branch.condition?.type === 'else'" class="else-desc">
          <el-text type="info">当以上所有条件都不满足时，执行此分支</el-text>
        </div>
        <!-- 默认显示（如果没有condition） -->
        <div v-else class="else-desc">
          <el-text type="warning">请配置分支条件</el-text>
        </div>
      </div>
    </div>

    <!-- 添加分支按钮 -->
    <div class="add-branch-action">
      <el-button type="primary" plain :icon="Plus" @click="addBranch">
        添加条件分支
      </el-button>
    </div>

    <!-- 提示信息 -->
    <el-alert
      title="使用说明"
      type="info"
      :closable="false"
      class="usage-tip"
    >
      <template #default>
        <ol>
          <li>条件按顺序从上到下匹配，执行第一个满足条件的分支</li>
          <li>ELSE 分支必须放在最后，当其他条件都不满足时执行</li>
          <li>每个分支内可以嵌套其他步骤，包括另一个条件分支</li>
        </ol>
      </template>
    </el-alert>
  </div>
</template>

<script setup>
import {ref, watch} from 'vue'
import {Share, Delete, Plus} from '@element-plus/icons-vue'
import {ElMessage} from 'element-plus'

const props = defineProps({
  branches: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['update:branches'])

// 本地分支数据 - 使用 ref 创建副本
const localBranches = ref([])

// 监听 props 变化，更新本地副本
watch(() => props.branches, (newBranches) => {
  // 使用深拷贝避免引用问题
  localBranches.value = JSON.parse(JSON.stringify(newBranches || []))
}, { immediate: true, deep: true })

// 更新分支的辅助函数
function updateBranches() {
  emit('update:branches', JSON.parse(JSON.stringify(localBranches.value)))
}

// 条件类型选项
const conditionTypes = [
  {label: '元素可见', value: 'element_visible'},
  {label: '元素存在', value: 'element_exist'},
  {label: '元素文本等于', value: 'element_text_equals'},
  {label: '元素文本包含', value: 'element_text_contains'},
  {label: '页面标题等于', value: 'page_title_equals'},
  {label: '页面URL包含', value: 'page_url_contains'},
  {label: '自定义JS表达式', value: 'custom_js'}
]

// 判断是否为元素相关条件
function isElementCondition(type) {
  return [
    'element_visible',
    'element_exist',
    'element_text_equals',
    'element_text_contains'
  ].includes(type)
}

// 判断是否为文本对比条件
function isTextCompareCondition(type) {
  return [
    'element_text_equals',
    'element_text_contains'
  ].includes(type)
}

// 添加分支
function addBranch() {
  // 找到 ELSE 分支的位置（应该在最后）
  const elseIndex = localBranches.value.findIndex(b => b.condition?.type === 'else')
  
  const newBranch = {
    id: `branch_${Date.now()}`,
    name: `分支${localBranches.value.length}`,
    condition: {
      type: 'element_visible',
      locator: '',
      operator: 'is_true',
      expected_value: ''
    },
    steps: []
  }
  
  // 在 ELSE 分支之前插入
  if (elseIndex >= 0) {
    localBranches.value.splice(elseIndex, 0, newBranch)
  } else {
    localBranches.value.push(newBranch)
  }
  
  // 触发更新
  updateBranches()
  ElMessage.success('分支已添加')
}

// 删除分支
function removeBranch(index) {
  const branch = localBranches.value[index]
  
  if (branch.condition?.type === 'else') {
    ElMessage.warning('ELSE 分支不能删除')
    return
  }
  
  localBranches.value.splice(index, 1)
  
  // 触发更新
  updateBranches()
  ElMessage.success('分支已删除')
}
</script>

<style scoped lang="scss">
.condition-edit {
  padding: 10px;
}

.condition-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 20px;
  padding-bottom: 15px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  
  .title {
    font-size: 16px;
    font-weight: 500;
  }
}

.branches-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.branch-card {
  background: var(--el-fill-color-light);
  border-radius: 8px;
  border: 1px solid var(--el-border-color-lighter);
  overflow: hidden;
  
  &.is-else {
    background: #f5f7fa;
    border-style: dashed;
  }
}

.branch-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: #fff;
  border-bottom: 1px solid var(--el-border-color-lighter);
  
  .branch-title {
    display: flex;
    align-items: center;
    gap: 8px;
    flex: 1;
    
    .branch-name-input {
      width: 200px;
    }
  }
}

.condition-config {
  padding: 16px;
}

.else-desc {
  padding: 16px;
  text-align: center;
}

.add-branch-action {
  margin-top: 16px;
  text-align: center;
}

.usage-tip {
  margin-top: 20px;
  
  ol {
    margin: 8px 0 0 16px;
    padding: 0;
    
    li {
      margin-bottom: 4px;
      line-height: 1.6;
    }
  }
}
</style>
