<template>
  <PageCard>
    <template #title>
      <el-tabs v-model="activeTab" class="user-page-tabs">
        <el-tab-pane label="用户列表" name="users" />
        <el-tab-pane v-if="uStore.hasPermission('user:edit')" label="邀请码" name="invites" />
      </el-tabs>
      <el-button
        v-if="activeTab === 'users' && uStore.hasPermission('user:edit')"
        type="primary"
        size="small"
        @click="ClickAdd"
        icon="Plus"
      >用户</el-button>
      <el-button
        v-if="activeTab === 'invites' && uStore.hasPermission('user:edit')"
        type="primary"
        size="small"
        @click="openInviteDialog"
        icon="Plus"
      >生成邀请码</el-button>
    </template>
    <template #main>
      <template v-if="activeTab === 'users'">
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
          <el-table-column label="序号" type="index" :index="tableRowIndex" width="90"/>
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
          <el-table-column label="关联角色" width="180">
            <template #default="scope">
              <template v-if="scope.row.roles.length">
                <el-tag v-for="role in scope.row.roles" :key="role.id" type="primary" style="margin: 2px">{{ role.name }}</el-tag>
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

      <template v-else-if="activeTab === 'invites'">
        <el-table :data="inviteList" style="width: 100%" :header-cell-style="{'text-align':'center'}"
                  :cell-style="{'text-align':'center'}" stripe>
          <template #empty>
            <div class="table-empty"><div>暂无邀请码</div></div>
          </template>
          <el-table-column label="邀请码" prop="code" min-width="120">
            <template #default="scope">
              <el-tag type="success">{{ scope.row.code }}</el-tag>
              <el-button link type="primary" size="small" @click="copyText(scope.row.code)">复制</el-button>
            </template>
          </el-table-column>
          <el-table-column label="绑定角色" min-width="180">
            <template #default="scope">
              <el-tag v-for="name in roleNames(scope.row.role_ids)" :key="name" size="small" style="margin: 2px">{{ name }}</el-tag>
              <span v-if="!scope.row.role_ids?.length">普通成员（默认）</span>
            </template>
          </el-table-column>
          <el-table-column label="使用情况" width="120">
            <template #default="scope">
              {{ scope.row.used_count }} / {{ scope.row.max_uses <= 0 ? '∞' : scope.row.max_uses }}
            </template>
          </el-table-column>
          <el-table-column label="状态" width="90">
            <template #default="scope">
              <el-tag :type="scope.row.is_active ? 'success' : 'info'">{{ scope.row.is_active ? '启用' : '停用' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="note" label="备注" min-width="120" show-overflow-tooltip />
          <el-table-column prop="created_by_username" label="创建人" width="100" />
          <el-table-column label="过期时间" min-width="150">
            <template #default="scope">
              {{ scope.row.expires_at ? dateTools.rTime(scope.row.expires_at) : '永不过期' }}
            </template>
          </el-table-column>
          <el-table-column label="操作" width="160" fixed="right">
            <template #default="scope">
              <el-button size="small" @click="toggleInviteActive(scope.row)">{{ scope.row.is_active ? '停用' : '启用' }}</el-button>
              <el-button size="small" type="danger" @click="deleteInvite(scope.row.id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </template>
    </template>
    <template #bottom>
      <el-pagination
          v-if="activeTab === 'users'"
          v-model:current-page="pageConfig.page"
          v-model:page-size="pageConfig.size"
          :page-sizes="[10, 20, 30, 40]"
          layout="total, sizes, prev, pager, next, jumper"
          :total="pageConfig.total"
          @size-change="getUserList"
          @current-change="getUserList"/>
      <el-pagination
          v-else
          v-model:current-page="invitePage.page"
          v-model:page-size="invitePage.size"
          :page-sizes="[10, 20, 30, 40]"
          layout="total, sizes, prev, pager, next, jumper"
          :total="invitePage.total"
          @size-change="getInviteList"
          @current-change="getInviteList"/>
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
        <el-select v-model="register.roles" multiple placeholder="请选择关联角色（可多选组合）" style="width: 100%">
          <el-option v-for="role in roleList" :key="role.id" :label="roleLabel(role)" :value="role.id"/>
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
        <el-select v-model="update.roles" multiple placeholder="请选择关联角色（可多选组合）" style="width: 100%">
          <el-option v-for="role in roleList" :key="role.id" :label="roleLabel(role)" :value="role.id"/>
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

  <!-- 生成邀请码 -->
  <el-dialog v-model="inviteDialog" title="生成邀请码" width="560" center destroy-on-close>
    <el-form :model="inviteForm" label-width="100px">
      <el-form-item label="自定义码">
        <el-input v-model="inviteForm.code" placeholder="留空则自动生成 8 位" clearable maxlength="32" />
      </el-form-item>
      <el-form-item label="绑定角色">
        <el-select v-model="inviteForm.role_ids" multiple placeholder="不选则默认「普通成员」" style="width: 100%" clearable>
          <el-option v-for="role in roleList" :key="role.id" :label="roleLabel(role)" :value="role.id"/>
        </el-select>
        <div class="form-hint">可多选组合，如 Web测试 + 接口测试</div>
      </el-form-item>
      <el-form-item label="可用次数">
        <el-input-number v-model="inviteForm.max_uses" :min="1" :max="9999" />
      </el-form-item>
      <el-form-item label="过期时间">
        <el-date-picker
          v-model="inviteForm.expires_at"
          type="datetime"
          placeholder="留空则永不过期"
          value-format="YYYY-MM-DDTHH:mm:ss"
          style="width: 100%"
        />
      </el-form-item>
      <el-form-item label="备注">
        <el-input v-model="inviteForm.note" placeholder="可选" clearable />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="inviteDialog = false">取消</el-button>
      <el-button type="primary" @click="submitInvite">生成</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import {reactive, onMounted, ref, watch} from "vue"
import {User} from "@element-plus/icons-vue"
import http from '@/api/index'
import {ElNotification, ElMessageBox, ElMessage} from "element-plus"
import dateTools from "@/tools/dateTools.js"
import PageCard from "@/components/PageCard.vue"
import {UserStore} from '@/stores/module/UserStore'
import { makeTableRowIndex } from '@/utils/tableIndex'
import { copyToClipboard } from '@/utils/clipboard'

const uStore = UserStore()
const activeTab = ref('users')

let pageConfig = reactive({ page: 1, size: 10, total: 0 })
const tableRowIndex = makeTableRowIndex(pageConfig)
let invitePage = reactive({ page: 1, size: 10, total: 0 })

const showPassword1 = ref(false)
const showPassword2 = ref(false)
const userList = ref([])
const inviteList = ref([])
const roleList = ref([])

const createDialog = ref(false)
const updateDialog = ref(false)
const inviteDialog = ref(false)

const register = reactive({
  username: "",
  password: "",
  password_confirm: "",
  email: "",
  mobile: "",
  nickname: "",
  is_superuser: false,
  roles: []
})

const update = reactive({
  id: 0,
  username: "",
  nickname: "",
  email: "",
  mobile: "",
  is_superuser: false,
  is_active: true,
  roles: []
})

const inviteForm = reactive({
  code: "",
  role_ids: [],
  max_uses: 1,
  expires_at: null,
  note: ""
})

const formDataRef = ref()
const formUpdateRef = ref()

const formDataRules = reactive({
  username: [{required: true, message: '用户账号不能为空！', trigger: 'blur'}],
  password: [{required: true, message: '登录密码不能为空！', trigger: 'blur'}],
  password_confirm: [{required: true, message: '确认密码不能为空！', trigger: 'blur'}],
  nickname: [{required: true, message: '用户昵称不能为空！', trigger: 'blur'}],
  mobile: [{required: true, message: '手机号不能为空！', trigger: 'blur'}],
  email: [{required: true, message: '用户邮箱不能为空！', trigger: 'blur'}],
})

const formUpdateRules = reactive({
  username: [{required: true, message: '用户账号不能为空！', trigger: 'blur'}],
  nickname: [{required: true, message: '用户昵称不能为空！', trigger: 'blur'}],
  mobile: [{required: true, message: '手机号不能为空！', trigger: 'blur'}],
  email: [{required: true, message: '用户邮箱不能为空！', trigger: 'blur'}],
})

function roleLabel(role) {
  return role.is_system ? `${role.name}（系统）` : role.name
}

function roleNames(roleIds) {
  if (!roleIds?.length) return []
  const map = Object.fromEntries(roleList.value.map(r => [r.id, r.name]))
  return roleIds.map(id => map[id]).filter(Boolean)
}

async function copyText(text) {
  const ok = await copyToClipboard(text)
  if (ok) ElMessage.success('已复制到剪贴板')
  else ElMessage.warning('复制失败，请手动复制')
}

async function getRoleList() {
  const response = await http.roleApi.getRoleList({ page: 1, size: 200 })
  if (response.status === 200) {
    roleList.value = response.data.data
  }
}

async function getUserList() {
  const response = await http.userApi.getUserList(pageConfig)
  if (response.status === 200) {
    pageConfig.total = response.data.total
    userList.value = response.data.data
  }
}

async function getInviteList() {
  const response = await http.inviteCodeApi.getList(invitePage)
  if (response.status === 200) {
    invitePage.total = response.data.total
    inviteList.value = response.data.data
  }
}

watch(activeTab, (tab) => {
  if (tab === 'invites') getInviteList()
})

function ClickAdd() {
  Object.assign(register, {
    username: "", password: "", password_confirm: "", email: "", mobile: "",
    nickname: "", is_superuser: false, roles: []
  })
  createDialog.value = true
}

function EditDialog(row) {
  Object.assign(update, {
    id: row.id,
    username: row.username,
    nickname: row.nickname,
    email: row.email,
    mobile: row.mobile,
    is_superuser: row.is_superuser,
    is_active: row.is_active,
    roles: row.roles.map(r => r.id)
  })
  updateDialog.value = true
}

function openInviteDialog() {
  Object.assign(inviteForm, { code: "", role_ids: [], max_uses: 1, expires_at: null, note: "" })
  inviteDialog.value = true
}

async function createUser(elForm) {
  elForm.validate(async (valid) => {
    if (!valid) return
    const response = await http.userApi.createUser(register)
    if (response.status === 201) {
      ElNotification({ title: '创建成功', type: 'success' })
      createDialog.value = false
      getUserList()
    } else {
      ElNotification({ title: '创建失败', message: response.data?.detail, type: 'error' })
    }
  })
}

async function updateUser(elForm) {
  elForm.validate(async (valid) => {
    if (!valid) return
    const response = await http.userApi.updateUser(update.id, update)
    if (response.status === 200) {
      ElNotification({ title: '更新成功', type: 'success' })
      updateDialog.value = false
      getUserList()
    } else {
      ElNotification({ title: '更新失败', message: response.data?.detail, type: 'error' })
    }
  })
}

async function deleteUser(userId) {
  await ElMessageBox.confirm('确定删除该用户吗？', '提示', { type: 'warning' })
  const response = await http.userApi.deleteUser(userId)
  if (response.status === 204) {
    ElMessage.success('删除成功')
    getUserList()
  }
}

async function toggleActive(row) {
  const response = await http.userApi.toggleActive(row.id)
  if (response.status === 200) {
    ElMessage.success(response.data.detail)
    getUserList()
  }
}

async function submitInvite() {
  const payload = { ...inviteForm }
  if (!payload.expires_at) delete payload.expires_at
  const response = await http.inviteCodeApi.create(payload)
  if (response.status === 201) {
    ElNotification({ title: '邀请码已生成', message: response.data.code, type: 'success' })
    inviteDialog.value = false
    getInviteList()
  } else {
    ElNotification({ title: '生成失败', message: response.data?.detail, type: 'error' })
  }
}

async function toggleInviteActive(row) {
  const response = await http.inviteCodeApi.update(row.id, { is_active: !row.is_active })
  if (response.status === 200) {
    ElMessage.success('已更新')
    getInviteList()
  }
}

async function deleteInvite(id) {
  await ElMessageBox.confirm('确定删除该邀请码吗？', '提示', { type: 'warning' })
  const response = await http.inviteCodeApi.delete(id)
  if (response.status === 204) {
    ElMessage.success('已删除')
    getInviteList()
  }
}

onMounted(async () => {
  await getRoleList()
  await getUserList()
})
</script>

<style scoped>
.user-page-tabs {
  flex: 1;
  min-width: 0;
}
.user-page-tabs :deep(.el-tabs__header) {
  margin-bottom: 0;
}
.form-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}
</style>
