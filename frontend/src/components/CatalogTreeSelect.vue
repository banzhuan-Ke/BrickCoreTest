<template>
  <el-tree-select
    v-model="innerValue"
    :data="treeData"
    :props="{ label: 'name', value: 'id', children: 'children' }"
    check-strictly
    :clearable="clearable"
    :placeholder="placeholder"
    :disabled="disabled"
    :style="selectStyle"
    filterable
    @change="handleChange"
  />
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { catalogApi, buildCatalogTree } from '@/api/modules/catalog'

const props = defineProps({
  modelValue: {
    type: [Number, String, null],
    default: null
  },
  projectId: {
    type: [Number, String, null],
    default: null
  },
  placeholder: {
    type: String,
    default: '选择目录'
  },
  clearable: {
    type: Boolean,
    default: true
  },
  disabled: {
    type: Boolean,
    default: false
  },
  width: {
    type: String,
    default: '100%'
  }
})

const emit = defineEmits(['update:modelValue', 'change'])

const treeData = ref([])
const selectStyle = computed(() => ({ width: props.width }))

const innerValue = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val ?? null)
})

const loadTree = async () => {
  if (!props.projectId) {
    treeData.value = []
    return
  }
  try {
    const res = await catalogApi.getList({ project_id: props.projectId, tree: true })
    if (res.status === 200) {
      const data = res.data
      const hasNested = Array.isArray(data) && data.some(item => Array.isArray(item.children) && item.children.length > 0)
      treeData.value = hasNested ? data : buildCatalogTree(data || [])
    }
  } catch (error) {
    console.error('加载目录树失败:', error)
    treeData.value = []
  }
}

watch(() => props.projectId, loadTree, { immediate: true })

const handleChange = (val) => {
  emit('change', val ?? null)
}

defineExpose({ loadTree, treeData })
</script>
