<template>
  <PageCard>
    <template #title>
      <div class="project-title-row">
        <el-button @click="clickAdd" size="small" type="primary" icon="Plus">项目</el-button>
        <TableColumnPicker
          :items="pickerItems"
          @toggle="setColumnVisible"
          @reorder="setPickerOrder"
          @reset="resetColumns"
        />
      </div>
    </template>
    <template #main>
      <el-table :key="tableRenderKey" :data="ProList" style="width: 100%" :header-cell-style="{'text-align':'center'}"
                :cell-style="{'text-align':'center'}" stripe>
        <template #empty>
          <div class="table-empty">
            <div class="empty-icon">
              <el-icon :size="40" color="#909399"><FolderOpened /></el-icon>
            </div>
            <div>暂无数据，请先创建项目才可以使用项目下的菜单！</div>
          </div>
        </template>
        <template v-for="col in activeColumns" :key="col.key">
          <el-table-column
            v-if="col.key === 'index'"
            label="序号"
            type="index"
            :index="tableRowIndex"
            :width="col.width"
          />
          <el-table-column
            v-else-if="col.key === 'name'"
            prop="name"
            label="项目名称"
            :min-width="col.minWidth || 160"
          >
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
          <el-table-column
            v-else-if="col.key === 'username'"
            prop="username"
            label="创建人"
          />
          <el-table-column
            v-else-if="col.key === 'my_role'"
            label="我的角色"
            :width="col.width"
          >
            <template #default="scope">
              <el-tag v-if="scope.row.my_role" size="small" :type="roleTagType(scope.row.my_role)">
                {{ roleLabel(scope.row.my_role) }}
              </el-tag>
              <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column
            v-else-if="col.key === 'create_time'"
            label="创建时间"
            :width="col.width"
          >
            <template #default="scope">
              {{ dateTools.rTime(scope.row.create_time) }}
            </template>
          </el-table-column>
          <el-table-column
            v-else-if="col.key === 'update_time'"
            label="更新时间"
            :width="col.width"
          >
            <template #default="scope">
              {{ dateTools.rTime(scope.row.update_time) }}
            </template>
          </el-table-column>
        </template>
        <el-table-column label="操作" width="260" fixed="right">
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
              <el-tooltip v-if="row.can_manage_members" content="成员管理" placement="top">
                <el-button
                  circle
                  size="small"
                  type="info"
                  icon="UserFilled"
                  @click="openMemberDialog(row)"
                />
              </el-tooltip>
              <el-tooltip content="编辑" placement="top">
                <el-button
                  circle
                  size="small"
                  type="primary"
                  icon="Edit"
                  :disabled="!row.can_edit_project"
                  @click="clickEdit(row)"
                />
              </el-tooltip>
              <el-tooltip content="删除" placement="top">
                <el-button
                  circle
                  size="small"
                  type="danger"
                  icon="Delete"
                  :disabled="!row.can_delete_project || isCurrentProject(row)"
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

  <!-- 项目成员管理 -->
  <el-dialog v-model="memberDialogVisible" :title="`成员管理 - ${memberProject?.name || ''}`" width="760px" center destroy-on-close>
    <div v-if="memberProject?.can_manage_members" class="member-toolbar">
      <el-select
        v-model="addMemberForm.user_id"
        filterable
        placeholder="选择用户"
        style="width: 220px"
        clearable
      >
        <el-option
          v-for="u in candidateUsers"
          :key="u.id"
          :label="`${u.nickname}（${u.username}）`"
          :value="u.id"
        />
      </el-select>
      <el-select v-model="addMemberForm.role" style="width: 140px">
        <el-option v-for="r in assignableRoles" :key="r.value" :label="r.label" :value="r.value" />
      </el-select>
      <el-button type="primary" @click="submitAddMember">添加成员</el-button>
    </div>
    <el-table :data="memberList" stripe style="width: 100%; margin-top: 12px">
      <el-table-column prop="nickname" label="昵称" />
      <el-table-column prop="username" label="登录名" />
      <el-table-column label="项目角色" width="140">
        <template #default="scope">
          <el-select
            v-if="canEditMemberRole(scope.row)"
            v-model="scope.row.role"
            size="small"
            @change="(val) => changeMemberRole(scope.row, val)"
          >
            <el-option v-for="r in assignableRoles" :key="r.value" :label="r.label" :value="r.value" />
          </el-select>
          <el-tag v-else size="small">{{ roleLabel(scope.row.role) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="invited_by_username" label="邀请人" width="100" />
      <el-table-column label="操作" width="160">
        <template #default="scope">
          <el-button
            v-if="memberProject?.my_role === 'owner' && scope.row.role !== 'owner'"
            link
            type="warning"
            @click="transferTo(scope.row)"
          >设为负责人</el-button>
          <el-button
            v-if="canRemoveMember(scope.row)"
            link
            type="danger"
            @click="removeMember(scope.row)"
          >移除</el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-dialog>
</template>

<script setup>
import {ref, reactive, onMounted, computed} from 'vue'
import {FolderOpened, Delete, Plus} from "@element-plus/icons-vue"
import http from '@/api/index'
import {ElMessageBox, ElMessage, ElNotification} from 'element-plus'
import {UserStore} from '@/stores/module/UserStore'
import {ProjectStore} from "@/stores/module/ProjectStore.js"
import dateTools from '@/tools/dateTools'
import {useRouter} from 'vue-router'
import PageCard from "@/components/PageCard.vue"
import TableColumnPicker from '@/components/TableColumnPicker.vue'
import { useTableColumns } from '@/composables/useTableColumns.js'
import { makeTableRowIndex } from '@/utils/tableIndex'
import GlobalVarsEditor from '@/components/GlobalVarsEditor.vue'

const {
  activeColumns,
  pickerItems,
  tableRenderKey,
  setColumnVisible,
  setPickerOrder,
  resetColumns
} = useTableColumns('project.list')

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

const tableRowIndex = makeTableRowIndex(pageConfig)

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

const ROLE_LABELS = { owner: '负责人', manager: '管理员', member: '成员', viewer: '观察者' }
function roleLabel(role) { return ROLE_LABELS[role] || role || '-' }
function roleTagType(role) {
  if (role === 'owner') return 'danger'
  if (role === 'manager') return 'warning'
  if (role === 'viewer') return 'info'
  return 'primary'
}

const memberDialogVisible = ref(false)
const memberProject = ref(null)
const memberList = ref([])
const allUsers = ref([])
const assignableRoles = ref([])
const addMemberForm = reactive({ user_id: null, role: 'member' })

const candidateUsers = computed(() => {
  const memberIds = new Set(memberList.value.map(m => m.user_id))
  return allUsers.value.filter(u => !memberIds.has(u.id))
})

function canEditMemberRole(row) {
  if (!memberProject.value?.can_manage_members || row.role === 'owner') return false
  if (row.role === 'manager' && memberProject.value.my_role !== 'owner') return false
  return true
}

function canRemoveMember(row) {
  if (!memberProject.value?.can_manage_members || row.role === 'owner') return false
  if (row.role === 'manager' && memberProject.value.my_role !== 'owner') return false
  return row.user_id !== uStore.userInfo?.id
}

async function openMemberDialog(row) {
  memberProject.value = row
  memberDialogVisible.value = true
  addMemberForm.user_id = null
  addMemberForm.role = 'member'
  await Promise.all([loadMembers(row.id), loadUsersForMember(), loadAssignableRoles(row.id)])
}

async function loadMembers(projectId) {
  const res = await http.projectApi.getMembers(projectId, { page: 1, size: 200 })
  if (res.status === 200) memberList.value = res.data.data || []
}

async function loadUsersForMember() {
  if (!uStore.hasPermission('user:view')) return
  const res = await http.userApi.getUserList({ page: 1, size: 500 })
  if (res.status === 200) allUsers.value = res.data.data || []
}

async function loadAssignableRoles(projectId) {
  const res = await http.projectApi.getMemberRoles(projectId)
  if (res.status === 200) assignableRoles.value = res.data || []
}

async function submitAddMember() {
  if (!addMemberForm.user_id) {
    ElMessage.warning('请选择用户')
    return
  }
  const res = await http.projectApi.addMember(memberProject.value.id, { ...addMemberForm })
  if (res.status === 201) {
    ElMessage.success('成员已添加')
    addMemberForm.user_id = null
    await loadMembers(memberProject.value.id)
  }
}

async function changeMemberRole(row, role) {
  const res = await http.projectApi.updateMember(memberProject.value.id, row.id, { role })
  if (res.status !== 200) {
    await loadMembers(memberProject.value.id)
  } else {
    ElMessage.success('角色已更新')
  }
}

async function removeMember(row) {
  await ElMessageBox.confirm(`确定移除成员「${row.nickname}」吗？`, '提示', { type: 'warning' })
  const res = await http.projectApi.removeMember(memberProject.value.id, row.id)
  if (res.status === 204) {
    ElMessage.success('已移除')
    await loadMembers(memberProject.value.id)
  }
}

async function transferTo(row) {
  await ElMessageBox.confirm(`确定将项目负责人转让给「${row.nickname}」吗？`, '转让负责人', { type: 'warning' })
  const res = await http.projectApi.transferOwner(memberProject.value.id, { user_id: row.user_id })
  if (res.status === 200) {
    ElMessage.success('负责人已转让')
    memberDialogVisible.value = false
    await getProjectList()
  }
}
</script>

<style scoped>
.project-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
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

.member-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
</style>
