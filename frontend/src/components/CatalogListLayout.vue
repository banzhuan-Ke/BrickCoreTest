<template>
  <div class="catalog-list-layout">
    <aside class="catalog-list-sidebar">
      <CatalogTree
        :project-id="projectId"
        v-model="catalogId"
        :show-manage="showManage"
        :include-all-node="includeAllNode"
        :all-node-label="allNodeLabel"
        @change="(...args) => emit('change', ...args)"
      />
    </aside>
    <main class="catalog-list-main">
      <slot />
    </main>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import CatalogTree from '@/components/CatalogTree.vue'

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
    default: false
  },
  includeAllNode: {
    type: Boolean,
    default: true
  },
  allNodeLabel: {
    type: String,
    default: '全部'
  }
})

const emit = defineEmits(['update:modelValue', 'change'])

const catalogId = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})
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
}

.catalog-list-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
</style>
