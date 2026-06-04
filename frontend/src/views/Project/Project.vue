<template>
  <PageCard>
    <template #title>
      <el-button @click="clickAdd" size="small" type="primary" icon="Plus">项目</el-button>
    </template>
    <template #main>
      <el-table :data="ProList" style="width: 100%" :header-cell-style="{'text-align':'center'}"
                :cell-style="{'text-align':'center'}" stripe>
        <template #empty>
          <div class="table-empty">
            <div class="empty-icon">
              <el-icon :size="40" color="#909399"><FolderOpened /></el-icon>
            </div>
            <div>暂无数据，请先创建项目才可以使用项目下的菜单！</div>
          </div>
        </template>
        <el-table-column label="序号" type="index" width="90"/>
        <el-table-column prop="name" label="项目名称" min-width="160">
          <template #default="scope">
            <span class="project-name-cell">
              <span>{{ scope.row.name }}</span>
              <el-tag
                v-if="scope.row.is_user_default"
                type="warning"
                size="small"
                effect="plain"
                round
                class="default-badge"
              >登录默认</el-tag>
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="username" label="创建人"/>
        <el-table-column prop="create_time" label="创建时间">
          <template #default="scope">
            {{ dateTools.rTime(scope.row.create_time) }}
          </template>
        </el-table-column>
        <el-table-column label="更新时间">
          <template #default="scope">
            {{ dateTools.rTime(scope.row.update_time) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <div class="project-actions">
              <el-tooltip :content="isCurrentProject(row) ? '当前项目' : '切换项目'" placement="top">
                <el-button
                  circle
                  size="small"
                  type="success"
                  icon="Switch"
                  :disabled="isCurrentProject(row)"
                  @click="openProject(row)"
                />
              </el-tooltip>
              <el-tooltip
                v-if="!row.is_user_default"
                content="设为登录默认"
                placement="top"
              >
                <el-button
                  circle
                  size="small"
                  type="warning"
                  icon="Star"
                  @click="setDefaultProject(row)"
                />
              </el-tooltip>
              <el-tooltip v-else content="已是登录默认" placement="top">
                <el-button circle size="small" type="warning" icon="Star" disabled />
              </el-tooltip>
              <el-tooltip content="编辑" placement="top">
                <el-button
                  circle
                  size="small"
                  type="primary"
                  icon="Edit"
                  @click="clickEdit(row)"
                />
              </el-tooltip>
              <el-tooltip content="删除" placement="top">
                <el-button
                  circle
                  size="small"
                  type="danger"
                  icon="Delete"
                  :disabled="isCurrentProject(row)"
                  @click="clickDelete(row.id)"
                />
              </el-tooltip>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </template>
    <template #bottom>
      <el-pagination
          v-model:current-page="pageConfig.page"
          v-model:page-size="pageConfig.size"
          :page-sizes="[10, 20, 30, 40]"
          layout="total, sizes, prev, pager, next, jumper"
          :total="pageConfig.total"
          @current-change="getProjectList"
          @size-change="getProjectList"
      />
    </template>
  </PageCard>

  <!-- 添加项目-->
  <el-dialog v-model="isDlgShow" title="添加项目" width="30%" center destroy-on-close>
    <el-form :model="fromData" label-width="80" :rules="formDataRules" ref="formDataRef">
      <el-form-item label="项目名称：" prop="name" label-width="100px">
        <el-input @keyup.enter="creatPro" v-model="fromData.name" autocomplete="off" placeholder="请输入项目名称"/>
      </el-form-item>
      <el-form-item label="创建人：" prop="username" label-width="100px">
        <el-input v-model="fromData.username" disabled autocomplete="off" placeholder="创建人"/>
      </el-form-item>
    </el-form>
    <template #footer>
      <div class="dialog-footer" style="text-align: center;">
        <el-button type="primary" @click="creatPro(formDataRef)">确认</el-button>
        <el-button @click="isDlgShow = false" plain>取消</el-button>
      </div>
    </template>
  </el-dialog>

  <!-- 修改项目的弹框 -->
  <el-dialog v-model="isUpdateDlgShow" title="编辑项目" width="720px" center destroy-on-close>
    <el-form :model="fromUpdateData" label-width="80" :rules="formUpdateDataRules" ref="formUpdateDataRef">
      <el-form-item label="项目名称：" prop="name" label-width="100px">
        <el-input @keyup.enter="updatePro" v-model="fromUpdateData.name" autocomplete="off"
                  placeholder="请输入项目名称"/>
      </el-form-item>
      <el-form-item label="创建人：" prop="username" label-width="100px">
        <el-input v-model="fromUpdateData.username" disabled autocomplete="off" placeholder="创建人"/>
      </el-form-item>
      <el-form-item label="全局变量：" label-width="100px">
        <GlobalVarsEditor ref="projectVarsEditorRef" v-model="projectGlobalVars" json-height="220px" />
        <div class="field-hint">项目级默认值；与环境变量同名时，执行以环境变量为准</div>
      </el-form-item>
    </el-form>
    <template #footer>
      <div class="dialog-footer" style="text-align: center;">
        <el-button type="primary" @click="updatePro(formUpdateDataRef)">确认</el-button>
        <el-button @click="isUpdateDlgShow = false">取消</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import {ref, reactive, onMounted} from 'vue'
import {FolderOpened, Delete, Plus} from "@element-plus/icons-vue"
import http from '@/api/index'
import {ElMessageBox, ElMessage, ElNotification} from 'element-plus'
import {UserStore} from '@/stores/module/UserStore'
import {ProjectStore} from "@/stores/module/ProjectStore.js"
import dateTools from '@/tools/dateTools'
import {useRouter} from 'vue-router'
import PageCard from "@/components/PageCard.vue"
import GlobalVarsEditor from '@/components/GlobalVarsEditor.vue'

const uStore = UserStore()
const proStore = ProjectStore()
const router = useRouter()
// 获取项目列表数据
const ProList = ref([])

const pageConfig = reactive({
  page: 1,
  size: 10,
  total: 0
})

// 获取项目数据
const getProjectList = async () => {
  const res = await http.projectApi.getProjectList(pageConfig)
  ProList.value = res.data.data
  pageConfig.total = res.data.total
}

// 挂载数据
onMounted(() => {
  getProjectList()
})
// 删除项目
const clickDelete = (pro_id) => {
  // 调用后端的接口进行删除
  ElMessageBox.confirm(
      '此操作不可恢复，请确认是否要删除该项目?',
      '提示', {
        confirmButtonText: '确认',
        cancelButtonText: '取消',
        center: true,
        type: 'warning',
      })
      .then(async () => {
        // 调用后端接口进行删除
        const response = await http.projectApi.deleteProject(pro_id)
        if (response.status === 204) {
          ElNotification({
            title: '项目删除成功！',
            type: 'success',
            duration: 1500
          })
          // 刷新页面数据
          await getProjectList()
        } else {
          ElNotification({
            title: '项目删除失败！',
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

// 创建项目
let isDlgShow = ref(false)
let fromData = reactive({
  name: "",
  user: uStore.userInfo.id,
  username: uStore.userInfo.username
})
// 显示添加窗口
const clickAdd = () => {
  // 重置表单数据
  fromData.name = ""
  isDlgShow.value = true
}
// 校验项目名称
const formDataRules = reactive({
  name: [{required: true, message: '项目名称不能为空！', trigger: 'blur'}]
})
// 表单引用对象
const formDataRef = ref()

// 发送请求添加项目
async function creatPro(elForm) {
  elForm.validate(async function (res) {
    if (!res) return
    const response = await http.projectApi.createProject(fromData)
    if (response.status === 201) {
      // 弹出提示
      ElNotification({
        title: '已成功创建项目！',
        type: 'success',
        duration: 1500,
      })
      // 关闭窗口
      isDlgShow.value = false
      // 刷新页面数据
      await getProjectList()
    } else {
      ElNotification({
        title: '项目创建失败！',
        type: 'error',
        duration: 1500,
        message: response.data.detail
      })
    }
  })
}

// 编辑项目
let isUpdateDlgShow = ref(false)
let fromUpdateData = ref({
  name: ""
})
// 项目全局变量（GlobalVarsEditor 绑定对象）
const projectGlobalVars = ref({})
const projectVarsEditorRef = ref(null)

function syncProjectVars(globalVars) {
  projectGlobalVars.value =
    globalVars && typeof globalVars === 'object' && !Array.isArray(globalVars)
      ? { ...globalVars }
      : {}
}

function clickEdit(pro) {
  isUpdateDlgShow.value = true
  fromUpdateData.value = {...pro}
  syncProjectVars(pro.global_vars)
}

// 校验项目名称
const formUpdateDataRules = reactive({
  name: [{required: true, message: '项目名称不能为空！', trigger: 'blur'}]
})
// 表单引用对象
const formUpdateDataRef = ref()

// 发送请求修改项目信息
async function updatePro(elForm) {
  elForm.validate(async function (res) {
    if (!res) return
    let pro_id = fromUpdateData.value.id
    const global_vars = projectVarsEditorRef.value?.validateAndGet?.()
    if (global_vars === null) return
    const payload = {...fromUpdateData.value, global_vars}
    const response = await http.projectApi.updateProject(pro_id, payload)
    if (response.status === 200) {
      ElNotification({
        title: '项目修改成功！',
        message: `新项目名称为：${fromUpdateData.value.name}`,
        type: 'success',
        duration: 1500
      })
      // 关闭窗口
      isUpdateDlgShow.value = false
      // 刷新页面上的数据
      await getProjectList()
      if (proStore.projectInfo?.id === pro_id) {
        await proStore.refreshProjectGlobals()
      }
    } else {
      ElNotification({
        title: '项目修改失败！',
        type: 'error',
        duration: 1500,
        message: response.data.detail
      })
    }
  })
}

// 打开项目
const openProject = async (pro) => {
  proStore.$reset()
  await proStore.applyProject(pro)
  ElNotification({
    title: '项目切换成功！',
    type: 'success',
    message: `当前测试项目名称为：${pro.name}`,
    duration: 1500,
    offset: 50
  })
  router.push({ name: 'environmentList' })
}

const setDefaultProject = async (pro) => {
  try {
    const res = await http.projectApi.setDefaultProject(pro.id)
    if (res.status === 200) {
      uStore.userInfo = { ...uStore.userInfo, default_project_id: pro.id }
      ElMessage.success(`已将「${pro.name}」设为登录默认项目`)
      await getProjectList()
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '设置失败')
  }
}

const isCurrentProject = (row) => row.id === proStore.projectInfo?.id
</script>

<style scoped>
.field-hint {
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.project-name-cell {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  flex-wrap: wrap;
}

.default-badge {
  flex-shrink: 0;
}

.project-actions {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  flex-wrap: nowrap;
}
</style>
