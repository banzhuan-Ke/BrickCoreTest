<template>
  <div class="step-selector">
    <!-- 分类筛选 -->
    <div class="category-filter">
      <el-radio-group v-model="selectedCategory" size="small">
        <el-radio-button label="all">全部</el-radio-button>
        <el-radio-button label="browser">浏览器</el-radio-button>
        <el-radio-button label="navigation">导航</el-radio-button>
        <el-radio-button label="element">元素操作</el-radio-button>
        <el-radio-button label="assertion">断言</el-radio-button>
        <el-radio-button label="control">流程控制</el-radio-button>
      </el-radio-group>
    </div>
    
    <!-- 关键字列表 -->
    <div class="keyword-grid">
      <div
        v-for="keyword in filteredKeywords"
        :key="keyword.method"
        class="keyword-card"
        @click="selectKeyword(keyword)"
      >
        <div class="keyword-icon">
          <el-icon :size="24">
            <component :is="keyword.icon" />
          </el-icon>
        </div>
        <div class="keyword-info">
          <div class="keyword-name">{{ keyword.name }}</div>
          <div class="keyword-desc">{{ keyword.desc }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import {
  ChromeFilled,
  Position,
  Mouse,
  CircleCheck,
  Refresh,
  SwitchButton,
  Check
} from '@element-plus/icons-vue'

const emit = defineEmits(['select'])

const selectedCategory = ref('all')

// 关键字列表（可以从后端获取）
const keywords = [
  // 浏览器操作
  { 
    name: '打开浏览器', 
    method: 'open_browser', 
    category: 'browser',
    icon: ChromeFilled,
    desc: '启动指定浏览器',
    params: { browser_type: 'chromium' }
  },
  { 
    name: '关闭浏览器', 
    method: 'close_browser', 
    category: 'browser',
    icon: ChromeFilled,
    desc: '关闭当前浏览器',
    params: {}
  },
  
  // 导航操作
  { 
    name: '访问页面', 
    method: 'goto', 
    category: 'navigation',
    icon: Position,
    desc: '跳转到指定URL',
    params: { url: '', timeout: 30000, wait_until: 'load' }
  },
  { 
    name: '返回上一页', 
    method: 'go_back', 
    category: 'navigation',
    icon: Position,
    desc: '浏览器后退',
    params: {}
  },
  { 
    name: '刷新页面', 
    method: 'reload', 
    category: 'navigation',
    icon: Refresh,
    desc: '刷新当前页面',
    params: {}
  },
  
  // 元素操作
  { 
    name: '点击元素', 
    method: 'click', 
    category: 'element',
    icon: Mouse,
    desc: '点击指定元素',
    params: { selector: '' }
  },
  { 
    name: '输入文本', 
    method: 'fill', 
    category: 'element',
    icon: Mouse,
    desc: '在输入框中输入文本',
    params: { selector: '', value: '' }
  },
  { 
    name: '清空输入框', 
    method: 'clear', 
    category: 'element',
    icon: Mouse,
    desc: '清空输入框内容',
    params: { selector: '' }
  },
  
  // 断言
  { 
    name: '元素可见', 
    method: 'assert_visible', 
    category: 'assertion',
    icon: Check,
    desc: '断言元素可见',
    params: { selector: '' }
  },
  { 
    name: '文本包含', 
    method: 'assert_text_contains', 
    category: 'assertion',
    icon: Check,
    desc: '断言页面包含指定文本',
    params: { text: '' }
  },
  
  // 流程控制
  { 
    name: '条件判断', 
    method: 'if', 
    category: 'control',
    icon: SwitchButton,
    desc: '条件分支控制',
    params: { condition: '' },
    isContainer: true
  },
  { 
    name: '循环执行', 
    method: 'for', 
    category: 'control',
    icon: Refresh,
    desc: '循环执行子步骤',
    params: { times: 1 },
    isContainer: true
  }
]

// 筛选后的关键字
const filteredKeywords = computed(() => {
  if (selectedCategory.value === 'all') {
    return keywords
  }
  return keywords.filter(k => k.category === selectedCategory.value)
})

// 选择关键字
function selectKeyword(keyword) {
  emit('select', {
    keyword: keyword.name,
    desc: keyword.desc,
    method: keyword.method,
    params: { ...keyword.params },
    isContainer: keyword.isContainer || false
  })
}
</script>

<style scoped lang="scss">
.step-selector {
  padding: 16px;
}

.category-filter {
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--el-border-color);
}

.keyword-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
}

.keyword-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
  
  &:hover {
    border-color: var(--el-color-primary);
    background: var(--el-color-primary-light-9);
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  }
}

.keyword-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  background: white;
  border-radius: 8px;
  color: var(--el-color-primary);
}

.keyword-info {
  flex: 1;
}

.keyword-name {
  font-weight: 500;
  color: var(--el-text-color-primary);
  margin-bottom: 4px;
}

.keyword-desc {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
