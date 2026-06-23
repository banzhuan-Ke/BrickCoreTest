<template>
  <PageCard>
    <template #title>
      <span>测试套件列表</span>
    </template>
    <template #main>
      <div class="suite-toolbar">
        <el-input
          v-model="searchName"
          placeholder="按套件名称搜索"
          clearable
          @clear="handleSearch"
          @keyup.enter="handleSearch"
        >
          <template #append>
            <el-button icon="Search" @click="handleSearch" />
          </template>
        </el-input>
        <div class="suite-toolbar-hint">已加入当前计划的套件会标记为「已加入」</div>
      </div>
      <div class="main_box" v-infinite-scroll="loadNextPage">
        <draggable
            v-model="SuiteList" item-key="id"
            :sort="false"
            :clone="customClone"
            :group="{ name: 'suite', pull: 'clone', put: false }"
            chosen-class="chosen"
            drag-class="dragging"
            ghost-class="ghost">
          <template #item="{ element }">
            <div class="line" :class="{ 'line--added': isSuiteInPlan(element.id) }">
              <div class="module">
                <el-tag :type="isSuiteInPlan(element.id) ? 'success' : 'primary'">
                  {{ element.module }}
                </el-tag>
              </div>
              <div class="name">
                {{ element.name }}
                <el-tag
                  v-if="isSuiteInPlan(element.id)"
                  type="success"
                  size="small"
                  effect="plain"
                  class="added-tag"
                >
                  已加入
                </el-tag>
              </div>
              <div class="create_time">
                {{ dateTools.rTime(element.create_time) }}
              </div>
              <el-tooltip class="box-item" effect="dark" content="编辑当前的测试套件" placement="bottom">
                <el-button @click="router.push({name: 'editSuite', params: {id: element.id}})" icon="Edit" circle plain
                           type="primary"></el-button>
              </el-tooltip>
            </div>
          </template>
        </draggable>
        <div v-if="!loading && SuiteList.length === 0" class="empty-tip">
          {{ searchName.trim() ? '未找到匹配的套件' : '暂无套件' }}
        </div>
        <!--显示加载状态-->
        <div v-loading="loading" element-loading-text="加载中..." class="loading"></div>
      </div>
    </template>
  </PageCard>
</template>

<script setup>
import {reactive, ref, onMounted, inject, computed} from "vue"
import PageCard from "@/components/PageCard.vue"
import http from "@/api/index.js"
import {ProjectStore} from "@/stores/module/ProjectStore.js"
import draggable from 'vuedraggable'
import dateTools from '@/tools/dateTools'
import {useRouter} from "vue-router"

const router = useRouter()

const SuiteList = reactive([])
const proStore = ProjectStore()
const loading = ref(false)
const searchName = ref('')

const taskAddedSuiteIds = inject('taskAddedSuiteIds', computed(() => new Set()))

const isSuiteInPlan = (suiteId) => taskAddedSuiteIds.value.has(suiteId)

const pageConfig = reactive({
  page: 1,
  size: 10,
  total: 0,
  project: proStore.projectInfo.id,
  name: undefined,
})

onMounted(() => {
  getSuiteList()
})

const getSuiteList = async () => {
  loading.value = true
  try {
    const params = {
      page: pageConfig.page,
      size: pageConfig.size,
      project: pageConfig.project,
    }
    if (pageConfig.name) {
      params.name = pageConfig.name
    }
    const res = await http.suiteApi.getList(params)
    SuiteList.push(...res.data.data)
    pageConfig.total = res.data.total
  } finally {
    loading.value = false
  }
}

const customClone = (data) => {
  return {
    suite_id: data.id,
    suite_name: data.name
  }
}

const resetAndLoad = async () => {
  pageConfig.page = 1
  pageConfig.total = 0
  SuiteList.splice(0, SuiteList.length)
  await getSuiteList()
}

const handleSearch = () => {
  const keyword = searchName.value.trim()
  pageConfig.name = keyword || undefined
  resetAndLoad()
}

const loadNextPage = () => {
  if (loading.value) return
  if (pageConfig.page * pageConfig.size < pageConfig.total) {
    pageConfig.page += 1
    getSuiteList()
  }
}
</script>

<style scoped lang="scss">
@use "./SuiteSet.scss";
</style>
