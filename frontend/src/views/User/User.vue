<template>
  <PageCard>
    <template #title>
      <el-button v-if="uStore.hasPermission('user:edit')" type="primary" size="small" @click="ClickAdd" icon="Plus">用户</el-button>
    </template>
    <template #main>
      <el-table :data="userList" style="width: 100%" :header-cell-style="{'text-align':'center'}"
                :cell-style="{'text-align':'center'}" stripe>
        <template #empty>
          <div class="table-empty">
            <div class="empty-icon">
              <el-icon :size="40" color="#909399"><User /></el-icon>
            </div>
            <div>暂无数据</div>
          </div>
        </template>
        <el-table-column label="序号" type="index" width="90"/>
        <el-table-column prop="username" label="登录名"/>
        <el-table-column prop="nickname" label="用户昵称"/>
        <el-table-column prop="email" label="用户邮箱" min-width="150"/>
        <el-table-column prop="mobile" label="手机号"/>
        <el-table-column prop="is_superuser" label="管理员">
          <template #default="scope">
            <el-tag v-if="scope.row.is_superuser === true" type="primary">是</el-tag>
            <el-tag v-else-if="scope.row.is_superuser === false" type="info">否</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="关联角色" width="150">
          <template #default="scope">
            <template v-if="scope.row.roles.length">
              <el-tag v-for="role in scope.row.roles" :key="role.id" type="primary">{{ role.name }}</el-tag>
            </template>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="状态">
          <template #default="scope">
            <el-tag v-if="scope.row.is_active === true" type="primary">启用</el-tag>
            <el-tag v-else-if="scope.row.is_active === false" type="danger">禁用</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" min-width="150">
          <template #default="scope">
            {{ dateTools.rTime(scope.row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="更新时间" min-width="150">
          <template #default="scope">
            {{ dateTools.rTime(scope.row.update_time) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="scope">
            <el-button-group v-if="uStore.hasPermission('user:edit')">
              <el-button type="primary" size="small" @click="EditDialog(scope.row)" title="编辑">
                <el-icon><Edit /></el-icon>
              </el-button>
              <el-button 
                :type="scope.row.is_active ? 'warning' : 'success'" 
                size="small"
                @click="toggleActive(scope.row)" 
                :title="scope.row.is_active ? '停用' : '启用'">
                <el-icon><component :is="scope.row.is_active ? 'CircleClose' : 'CircleCheck'" /></el-icon>
              </el-button>
              <el-button type="danger" size="small" @click="deleteUser(scope.row.id)" title="删除">
                <el-icon><Delete /></el-icon>
              </el-button>
            </el-button-group>
            <span v-else>-</span>
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
          @size-change="getUserList"
          @current-change="getUserList"/>
    </template>
  </PageCard>

  <!--新建用户信息-->
  <el-dialog v-model="createDialog" title="添加用户" width="600" center destroy-on-close>
    <el-form :model="register" :rules="formDataRules" ref="formDataRef" label-width="auto" style="max-width: 600px">
      <el-form-item label="登录名：" prop="username">
        <el-input v-model="register.username" placeholder="请输入登录名" clearable/>
      </el-form-item>
      <el-form-item label="用户昵称：" prop="nickname">
        <el-input v-model="register.nickname" placeholder="请输入用户昵称" clearable/>
      </el-form-item>
      <el-form-item label="登录密码：" prop="password">
        <el-input v-model="register.password" placeholder="请输入登录密码" :type="showPassword1 ? 'text' : 'password'"
                  clearable>
          <template #suffix>
            <el-icon @click="showPassword1 = !showPassword1" style="cursor: pointer;">
              <component :is="showPassword1 ? 'View':'Hide' "/>
            </el-icon>
          </template>
        </el-input>
      </el-form-item>
      <el-form-item label="确认密码：" prop="password_confirm">
        <el-input v-model="register.password_confirm" placeholder="请再次输入密码"
                  :type="showPassword2 ? 'text' : 'password'" clearable>
          <template #suffix>
            <el-icon @click="showPassword2 = !showPassword2" style="cursor: pointer;">
              <component :is="showPassword2 ? 'View':'Hide' "/>
            </el-icon>
          </template>
        </el-input>
      </el-form-item>
      <el-form-item label="用户邮箱：" prop="email">
        <el-input v-model="register.email" placeholder="请输入用户邮箱" clearable/>
      </el-form-item>
      <el-form-item label="手机号：" prop="mobile">
        <el-input v-model="register.mobile" placeholder="请输入手机号" clearable/>
      </el-form-item>
      <el-form-item label="关联角色：">
        <el-select v-model="register.roles" multiple placeholder="请选择关联角色">
          <el-option v-for="role in roleList" :key="role.id" :label="role.name" :value="role.id"/>
        </el-select>
      </el-form-item>
      <el-form-item label="管理员：">
        <el-switch v-model="register.is_superuser"/>
      </el-form-item>
      <div style="text-align: center">
        <el-button type="primary" @click="createUser(formDataRef)" plain>保存</el-button>
        <el-button @click="createDialog=false" plain>取消</el-button>
      </div>
    </el-form>
  </el-dialog>
  <!--修改用户信息-->
  <el-dialog v-model="updateDialog" title="编辑用户" width="600" center destroy-on-close>
    <el-form :model="update" :rules="formUpdateRules" ref="formUpdateRef" label-width="auto" style="max-width: 600px">
      <el-form-item label="登录名：" prop="username">
        <el-input v-model="update.username" placeholder="请输入登录名" clearable/>
      </el-form-item>
      <el-form-item label="用户昵称：" prop="nickname">
        <el-input v-model="update.nickname" placeholder="请输入用户昵称" clearable/>
      </el-form-item>
      <el-form-item label="用户邮箱：" prop="email">
        <el-input v-model="update.email" placeholder="请输入用户邮箱" clearable/>
      </el-form-item>
      <el-form-item label="手机号：" prop="mobile">
        <el-input v-model="update.mobile" placeholder="请输入手机号" clearable/>
      </el-form-item>
      <el-form-item label="关联角色：">
        <el-select v-model="update.roles" multiple placeholder="请选择关联角色">
          <el-option v-for="role in roleList" :key="role.id" :label="role.name" :value="role.id"/>
        </el-select>
      </el-form-item>
      <el-form-item label="管理员：">
        <el-switch v-model="update.is_superuser"/>
      </el-form-item>
      <el-form-item label="状态：">
        <el-switch 
          v-model="update.is_active" 
          active-text="启用" 
          inactive-text="停用"
          :active-value="true"
          :inactive-value="false"/>
      </el-form-item>
      <div style="text-align: center">
        <el-button type="primary" @click="updateUser(formUpdateRef)" plain>保存</el-button>
        <el-button @click="updateDialog=false" plain>取消</el-button>
      </div>
    </el-form>
  </el-dialog>
</template>

<script setup>
import {reactive, onMounted, ref} from "vue"
import {User} from "@element-plus/icons-vue"
import http from '@/api/index'
import {ElNotification, ElMessageBox, ElMessage} from "element-plus"
import dateTools from "@/tools/dateTools.js"
import PageCard from "@/components/PageCard.vue"
import {UserStore} from '@/stores/module/UserStore'

const uStore = UserStore()

// 分页数据
let pageConfig = reactive({
  page: 1,
  size: 10,
  total: 0
})
// 定义密码是否显示
const showPassword1 = ref(false)
const showPassword2 = ref(false)
// 用户列表
let userList = ref([])
// 新建用户信息
let register = reactive({
  id: 0,
  username: "",
  email: "",
  nickname: "",
  password: "",
  password_confirm: "",
  mobile: "",
  is_superuser: false,
  roles: []
})
// 修改用户信息
let update = reactive({
  id: 0,
  username: "",
  email: "",
  nickname: "",
  mobile: "",
  is_superuser: false,
  is_active: true,
  roles: []
})
// 挂载数据，初始化数据
onMounted(async () => {
  await getRoleList()
  await getUserList()
})

// 获取角色列表方法
const roleList = ref([])

const getRoleList = async () => {
  const response = await http.roleApi.getRoleList(pageConfig)
  if (response.status === 200) {
    pageConfig.total = response.data.total
    roleList.value = response.data.data
  }
}
// 获取用户列表
const getUserList = async () => {
  const response = await http.userApi.getUserList(pageConfig)
  if (response.status === 200) {
    pageConfig.total = response.data.total
    userList.value = response.data.data
  }
}
// 新建用户表单校验
const formDataRules = reactive({
  username: [
    {required: true, message: '请输入登录名', trigger: 'blur'},
    {max: 10, message: '登录名不得超过10个字符', trigger: 'blur'},
  ],
  email: [
    {required: true, message: '请输入用户邮箱', trigger: 'blur'},
    {max: 255, message: '用户邮箱不得超过255个字符', trigger: 'blur'},
  ],
  nickname: [
    {required: true, message: '请输入用户昵称', trigger: 'blur'},
    {max: 20, message: '用户昵称不得超过20个字符', trigger: 'blur'},
  ],
  password: [
    {required: true, message: '请输入登录密码', trigger: 'blur'},
    {max: 20, message: '密码不得超过20个字符', trigger: 'blur'},
  ],
  password_confirm: [
    {required: true, message: '请再次输入密码', trigger: 'blur'},
    {max: 20, message: '密码不得超过20个字符', trigger: 'blur'},
  ],
  mobile: [
    {required: true, message: '请输入手机号', trigger: 'blur'},
    {max: 20, message: '手机号不得超过20个字符', trigger: 'blur'},
  ],
})

let createDialog = ref(false)
const formDataRef = ref()

// 点击添加按钮
function ClickAdd() {
  // 重置表单数据
  Object.assign(register, {
    id: 0,
    username: "",
    email: "",
    nickname: "",
    password: "",
    password_confirm: "",
    mobile: "",
    is_superuser: false,
    roles: []
  })
  createDialog.value = true
}

// 新建用户
async function createUser() {
  const valid = await formDataRef.value.validate().catch(() => false)
  if (!valid) return
  // 编辑模式下调用新建接口
  const response = await http.userApi.createUser(register)
  if (response.status === 201) {
    createDialog.value = false
    ElNotification({
      type: 'success',
      title: '已成功新建用户！',
      message: `用户账号为：${register.username}`,
      duration: 1500,
    })
    await getUserList()
  } else {
    ElNotification({
      title: '新建用户失败！',
      message: response.data.detail,
      type: 'error',
      duration: 1500
    })
  }
}

let updateDialog = ref(false)

// 点击编辑按钮
function EditDialog(row) {
  updateDialog.value = true;
  update.id = row.id
  update.username = row.username
  update.email = row.email
  update.nickname = row.nickname
  update.mobile = row.mobile
  update.is_superuser = row.is_superuser
  update.is_active = row.is_active
  update.roles = row.roles.map(role => role.id)
}

// 修改用户表单校验
const formUpdateRules = reactive({
  username: [
    {required: true, message: '请输入登录名', trigger: 'blur'},
    {max: 10, message: '登录名不得超过10个字符', trigger: 'blur'},
  ],
  email: [
    {required: true, message: '请输入用户邮箱', trigger: 'blur'},
    {max: 255, message: '用户邮箱不得超过255个字符', trigger: 'blur'},
  ],
  nickname: [
    {required: true, message: '请输入用户昵称', trigger: 'blur'},
    {max: 20, message: '用户昵称不得超过20个字符', trigger: 'blur'},
  ],
  mobile: [
    {required: true, message: '请输入手机号', trigger: 'blur'},
    {max: 20, message: '手机号不得超过20个字符', trigger: 'blur'},
  ],
})

// 表单引用对象
const formUpdateRef = ref()

// 修改用户
async function updateUser() {
  const valid = await formUpdateRef.value.validate().catch(() => false)
  if (!valid) return
  // 编辑模式下调用编辑接口
  const res = await http.userApi.updateUser(update.id, update)
  if (res.status === 200) {
    updateDialog.value = false
    ElNotification({
      type: 'success',
      title: '已成功修改用户！',
      duration: 1500,
    })
    await getUserList()
  } else {
    ElNotification({
      title: '修改用户失败！',
      message: res.data.detail,
      type: 'error',
      duration: 1500
    })
  }
}

// 启用/停用用户
async function toggleActive(row) {
  const action = row.is_active ? '停用' : '启用'
  ElMessageBox.confirm(
      `确认${action}用户 ${row.username} 吗？`,
      '提示', {
        confirmButtonText: '确认',
        cancelButtonText: '取消',
        center: true,
        type: 'warning'
      })
      .then(async () => {
        const response = await http.userApi.toggleActive(row.id)
        if (response.status === 200) {
          await getUserList()
          ElNotification({
            type: 'success',
            title: response.data.detail,
            duration: 1500
          })
        } else {
          ElNotification({
            title: `${action}失败！`,
            message: response.data.detail,
            type: 'error',
            duration: 1500
          })
        }
      })
      .catch(() => {
        ElMessage({
          type: 'info',
          message: `已取消${action}操作。`,
          duration: 1500,
        })
      })
}

// 删除用户
async function deleteUser(id) {
  ElMessageBox.confirm(
      '此操作不可恢复，确认删除该用户吗？',
      '提示', {
        confirmButtonText: '确认',
        cancelButtonText: '取消',
        center: true,
        type: 'warning'
      })
      .then(async () => {
        const response = await http.userApi.deleteUser(id)
        if (response.status === 204) {
          await getUserList()
          ElNotification({
            type: 'success',
            title: '删除成功！',
            duration: 1500
          })
        } else {
          ElNotification({
            title: '删除失败！',
            message: response.data.detail,
            type: 'error',
            duration: 1500
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
</script>

<style scoped>
</style>
