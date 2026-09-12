<template>
  <div class="catalog-list-layout" :class="{ 'is-collapsed': isCollapsed }">
    <aside class="catalog-list-sidebar" :class="{ 'is-collapsed': isCollapsed }">
      <div v-if="isCollapsed" class="catalog-rail" @click="expand">
        <el-tooltip content="展开测试目录" placement="right">
          <button type="button" class="rail-btn" aria-label="展开测试目录">
            <el-icon :size="18"><FolderOpened /></el-icon>
          </button>
        </el-tooltip>
        <span class="rail-label">目录</span>
      </div>
      <template v-else>
        <div class="sidebar-toolbar">
          <el-tooltip content="收起测试目录" placement="top">
            <button type="button" class="collapse-btn" aria-label="收起测试目录" @click="collapse">
              <el-icon :size="16"><DArrowLeft /></el-icon>
            </button>
          </el-tooltip>
        </div>
        <CatalogTree
          :project-id="projectId"
          v-model="catalogId"
          :show-manage="showManage"
          :include-all-node="includeAllNode"
          :all-node-label="allNodeLabel"
          :count-map="countMap"
          :show-search="showSearch"
          :fill-height="fillHeight"
          @change="(...args) => emit('change', ...args)"
          @changed="(...args) => emit('changed', ...args)"
        />
      </template>
    </aside>
    <main class="catalog-list-main">
      <slot />
    </main>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { DArrowLeft, FolderOpened } from '@element-plus/icons-vue'
import CatalogTree from '@/components/CatalogTree.vue'
import { useCatalogSidebarCollapse } from '@/composables/useCatalogSidebarCollapse'

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
    default: true
  },
  includeAllNode: {
    type: Boolean,
    default: true
  },
  allNodeLabel: {
    type: String,
    default: '全部'
  },
  countMap: {
    type: Object,
    default: () => ({})
  },
  showSearch: {
    type: Boolean,
    default: true
  },
  fillHeight: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:modelValue', 'change', 'changed'])

const catalogId = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

const { isCollapsed, expand, collapse } = useCatalogSidebarCollapse()
</script>

<style scoped lang="scss">
.catalog-list-layout {
  display: flex;
  gap: 16px;
  min-height: calc(100vh - 260px);
}

.catalog-list-sidebar {
  width: 260px;
  min-width: 260px;
  flex-shrink: 0;
  position: relative;
  transition: width 0.18s ease, min-width 0.18s ease;

  &.is-collapsed {
    width: 44px;
    min-width: 44px;
  }
}

.sidebar-toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 4px;
}

.collapse-btn,
.rail-btn {
  border: 1px solid var(--el-border-color-lighter);
  background: var(--el-bg-color);
  color: var(--el-text-color-secondary);
  border-radius: 6px;
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  padding: 0;

  &:hover {
    color: var(--el-color-primary);
    border-color: var(--el-color-primary-light-5);
    background: var(--el-color-primary-light-9);
  }
}

.catalog-rail {
  height: 100%;
  min-height: 220px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 8px 4px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-fill-color-blank);
  cursor: pointer;

  &:hover {
    border-color: var(--el-color-primary-light-5);
  }
}

.rail-label {
  writing-mode: vertical-rl;
  letter-spacing: 0.2em;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  user-select: none;
}

.catalog-list-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
</style>
