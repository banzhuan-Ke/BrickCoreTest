<template>
  <PageCard>
    <template #title>
      <span>测试套件列表</span>
    </template>
    <template #main>
      <div class="main_box" v-infinite-scroll="loadNextPage">
        <draggable
            v-model="SuiteList" item-key="index"
            :sort="false"
            :clone="customClone"
            :group="{ name: 'suite', pull: 'clone', put: false }"
            chosen-class="chosen"
            drag-class="dragging"
            ghost-class="ghost">
          <template #item="{ element, index }">
            <div class="line">
              <div class="module">
                <el-tag>{{ element.module }}</el-tag>
              </div>
              <div class="name">
                {{ element.name }}
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
        <!--显示加载状态-->
        <div v-loading="loading" element-loading-text="加载中..." class="loading"></div>
      </div>
    </template>
  </PageCard>
</template>

<script setup>
import {reactive, ref, onMounted} from "vue"
import PageCard from "@/components/PageCard.vue"
import http from "@/api/index.js"
import {ProjectStore} from "@/stores/module/ProjectStore.js"
import draggable from 'vuedraggable'
import dateTools from '@/tools/dateTools'
import {useRouter} from "vue-router"

const router = useRouter()

// 初始化SuiteList为响应式数组
const SuiteList = reactive([])
const proStore = ProjectStore()
const loading = ref(false)

const pageConfig = reactive({
  page: 1,
  size: 10,
  total: 0,
  project: proStore.projectInfo.id
})
// 初始化加载数据
onMounted(() => {
  getSuiteList()
})

// 获取套件数据
const getSuiteList = async () => {
  const res = await http.suiteApi.getList(pageConfig)
  SuiteList.push(...res.data.data)
  pageConfig.total = res.data.total
}

const customClone = (data) => {
  // 创建一个新的对象，避免直接引用原始对象
  return {
    suite_id: data.id,
    suite_name: data.name
  }
}

// 加载下一页
const loadNextPage = () => {
  if (pageConfig.page * pageConfig.size < pageConfig.total) {
    pageConfig.page += 1
    // 获取下一页
    getSuiteList()
  }
}
</script>

<style scoped lang="scss">
@use "./SuiteSet.scss";
</style>