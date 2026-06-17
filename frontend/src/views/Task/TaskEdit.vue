<template>
  <el-container>
    <!--  编辑测试计划-->
    <PageCard>
      <template #title>
        <span>测试计划中的套件信息</span>
      </template>
      <template #main>
        <el-form :model="taskInfo" label-width="auto" :rules="formUpdateDataRules" ref="formUpdateDataRef">
          <el-form-item label="计划名称：" prop="name">
            <el-input v-model="taskInfo.name" placeholder="请输入计划名称"></el-input>
          </el-form-item>
          <el-form-item label="所属目录">
            <CatalogTreeSelect
              v-model="taskInfo.catalog_id"
              :project-id="proStore.projectInfo.id"
              placeholder="请选择所属目录"
            />
          </el-form-item>
          <el-form-item label="创建人：" prop="username">
            <el-input v-model="taskInfo.username" disabled></el-input>
          </el-form-item>
          <el-form-item label="并行执行：">
            <el-switch v-model="taskInfo.parallel" active-text="套件按执行器权重分发" inactive-text="串行（单执行器）" />
            <div class="field-hint">开启后，运行计划时可选择多个执行器并设置权重；套件内用例仍串行。</div>
          </el-form-item>
        </el-form>
        <div class="title">测试计划中的套件</div>
        <div class="field-hint suite-order-hint">
          计划内各套件通常相互独立，执行顺序一般不影响测试结果；下方拖拽主要用于列表整理与移除管理。
        </div>
        <draggable
            v-model="taskInfo.suites" item-key="suite_id"
            :group="{ name: 'suite', pull: false, put: true }"
            handle=".sort_hand"
            @add="handleAdd"
            chosen-class="chosen"
            drag-class="dragging"
            ghost-class="ghost">
          <template #item="{ element, index }">
            <div class="lines">
              <div class="name">
                {{ element.suite_name }}
              </div>
              <div class="create_time">
                {{ dateTools.rTime(element.create_time) }}
              </div>
              <div class="btn">
                <el-tooltip class="box-item" effect="dark" content="拖拽套件在测试计划中的执行顺序" placement="bottom">
                  <el-button class="sort_hand" icon="Sort" circle type="success" plain></el-button>
                </el-tooltip>
                <el-tooltip class="box-item" effect="dark" content="移除测试计划中的套件" placement="bottom">
                  <el-button @click="deleteTaskSuite(element.suite_id)" icon="Delete" circle type="danger"
                             plain></el-button>
                </el-tooltip>
                <el-tooltip class="box-item" effect="dark" content="编辑当前的测试套件" placement="bottom">
                  <el-button @click="router.push({name: 'editSuite', params: {id: element.suite_id}})" icon="Edit"
                             circle type="primary" plain></el-button>
                </el-tooltip>
              </div>
            </div>
          </template>
        </draggable>
        <div class="line" style="cursor: pointer">
          <div class="info">
            可从测试套件集中拖拽套件到计划中
          </div>
        </div>
      </template>
      <template #bottom>
        <el-button @click="updateTask(formUpdateDataRef)" type="primary" plain icon="SuccessFilled">保存</el-button>
        <el-button @click="back()" plain icon="CircleCloseFilled">关闭</el-button>
      </template>
    </PageCard>
    <!--套件列表-->
    <SuiteSet></SuiteSet>
  </el-container>
</template>

<script setup>
import PageCard from "@/components/PageCard.vue"
import {useRoute, useRouter} from "vue-router"
import http from '@/api/index'
import {reactive, ref} from 'vue'
import SuiteSet from './componets/SuiteSet.vue'
import {ElNotification, ElMessageBox, ElMessage} from "element-plus"
import draggable from 'vuedraggable'
import {UserStore} from '@/stores/module/UserStore'
import {ProjectStore} from '@/stores/module/ProjectStore'
import CatalogTreeSelect from '@/components/CatalogTreeSelect.vue'
import dateTools from "@/tools/dateTools.js"

const uStore = UserStore()
const proStore = ProjectStore()
const route = useRoute()
const router = useRouter()
// 获取计划id
const taskId = route.params.id

// 获取计划详细数据
const taskInfo = reactive({
  "name": "",
  "catalog_id": null,
  "parallel": false,
  "suites": null,
})

// 获取计划详细数据
const getTaskDetail = async () => {
  const response = await http.taskApi.getTaskDetail(taskId)
  taskInfo.name = response.data.name
  taskInfo.catalog_id = response.data.catalog_id ?? null
  taskInfo.parallel = !!response.data.parallel
  taskInfo.username = response.data.username
  taskInfo.suites = response.data.suites
}
getTaskDetail()

// 校验计划
const formUpdateDataRules = reactive({
  name: [{required: true, message: '计划名称不能为空！', trigger: 'blur'}]
})
// 表单引用对象
const formUpdateDataRef = ref()

// 修改计划
async function updateTask(elForm) {
  elForm.validate(async function (res) {
    if (!res) return
    const response = await http.taskApi.updateTask(taskId, {
      name: taskInfo.name,
      catalog_id: taskInfo.catalog_id,
      parallel: taskInfo.parallel,
    })
    if (response.status !== 200) {
      ElNotification({
        title: '修改计划失败！',
        type: 'error',
        duration: 1500,
        message: response.data.detail
      })
      return
    }
    if (Array.isArray(taskInfo.suites) && taskInfo.suites.length) {
      const suiteRes = await http.taskApi.updateSuites(taskId, {
        suite_ids: taskInfo.suites.map((s) => s.suite_id),
      })
      if (suiteRes.status !== 200) {
        ElNotification({
          title: '套件顺序保存失败！',
          type: 'error',
          duration: 1500,
          message: suiteRes.data?.detail || '请重试',
        })
        return
      }
    }
    ElNotification({
      title: '修改计划成功！',
      type: 'success',
      duration: 1500
    })
    back()
  })
}

// 删除计划中的套件
const deleteTaskSuite = async (suite_id) => {
  ElMessageBox.confirm(
      '此操作不可恢复，确认删除该测试计划中的套件吗？',
      '提示', {
        confirmButtonText: '确认',
        cancelButtonText: '取消',
        center: true,
        type: 'warning'
      })
      .then(async () => {
        const response = await http.taskApi.deleteTaskSuite(taskId, suite_id)
        if (response.status === 204) {
          ElNotification({
            title: '已删除成功套件！',
            type: 'success',
            duration: 1500
          })
          await getTaskDetail()
        } else {
          ElNotification({
            title: '套件删除失败！',
            type: 'error',
            duration: 1500,
            message: response.data.detail
          })
        }
      })
      .catch(() => {
        ElMessage({
          type: 'info',
          message: '已取消删除操作。',
          duration: 1500,
        })
      })
}

// 往计划中添加套件
const handleAdd = async (event) => {
  const response = await http.taskApi.addTaskSuite(taskId, event.item._underlying_vm_.suite_id)
  if (response.status === 201) {
    ElNotification({
      title: '套件添加成功！',
      type: 'success',
      duration: 1500
    })
    await getTaskDetail()
  } else {
    ElNotification({
      title: '套件添加失败！',
      type: 'error',
      duration: 1500,
      message: response.data.detail
    })
  }
}

// 返回
const back = () => {
  router.back()
  // 删除标签页
  uStore.deleteTabs(route.path)
}
</script>

<style scoped lang="scss">
@use "./TaskEdit.scss";

.field-hint {
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}

.suite-order-hint {
  margin: 4px 0 12px;
}
</style>