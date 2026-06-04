<template>
  <PageCard>
    <template #title>
      <el-button v-if="uStore.hasPermission('role:edit')" type="primary" size="small" @click="ClickAdd" icon="Plus">角色</el-button>
    </template>
    <template #main>
      <el-table :data="roleList" style="width: 100%" :header-cell-style="{'text-align':'center'}"
                :cell-style="{'text-align':'center'}" stripe>
        <template #empty>
          <div class="table-empty">
            <div class="empty-icon">
              <el-icon :size="40" color="#909399"><UserFilled /></el-icon>
            </div>
            <div>暂无数据</div>
          </div>
        </template>
        <el-table-column label="序号" type="index" width="90"/>
        <el-table-column prop="name" label="角色名称"/>
        <el-table-column prop="description" label="角色描述"/>
        <el-table-column label="权限数量" width="100">
          <template #default="scope">
            <el-tag type="info" size="small">{{ scope.row.permissions ? scope.row.permissions.length : 0 }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="create_time" label="创建时间" min-width="150">
          <template #default="scope">
            {{ dateTools.rTime(scope.row.create_time) }}
          </template>
        </el-table-column>
        <el-table-column label="更新时间" min-width="150">
          <template #default="scope">
            {{ dateTools.rTime(scope.row.update_time) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200">
          <template #default="scope">
            <template v-if="uStore.hasPermission('role:edit')">
              <el-button type="primary" icon="Edit" @click="EditDialog(scope.row)" plain>编辑</el-button>
              <el-button @click="deleteRole(scope.row.id)" icon="Delete" type="danger" plain>删除</el-button>
            </template>
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
          @size-change="getRoleList"
          @current-change="getRoleList"/>
    </template>
  </PageCard>

  <!--新建/编辑角色信息-->
  <el-dialog v-model="createDialog" :title="isEdit ? '编辑角色' : '添加角色'" width="700" center destroy-on-close>
    <el-form :model="create" :rules="formDataRules" ref="formDataRef" label-width="auto" style="max-width: 650px">
      <el-form-item label="角色名称：" prop="name">
        <el-input v-model="create.name" placeholder="请输入角色名称" clearable/>
      </el-form-item>
      <el-form-item label="角色描述：" prop="description">
        <el-input v-model="create.description" placeholder="请输入角色描述" clearable/>
      </el-form-item>
      <el-form-item label="权限配置：">
        <el-card shadow="never" style="width: 100%;">
          <el-tree
            ref="permTreeRef"
            :data="permissionTree"
            show-checkbox
            node-key="value"
            :props="{ label: 'label', children: 'children' }"
            :default-checked-keys="create.permissions"
            :check-strictly="false"
            style="max-height: 300px; overflow-y: auto;"
          />
        </el-card>
      </el-form-item>
      <div style="text-align: center">
        <el-button type="primary" @click="saveRole(formDataRef)" plain>保存</el-button>
        <el-button @click="createDialog=false" plain>取消</el-button>
      </div>
    </el-form>
  </el-dialog>
</template>

<script setup>
import {reactive, onMounted, ref, nextTick} from "vue"
import {UserFilled} from "@element-plus/icons-vue"
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

// 角色列表
let roleList = ref([])
// 权限树数据
let permissionTree = ref([])
// 权限树引用
const permTreeRef = ref()
// 是否为编辑模式
const isEdit = ref(false)
// 新建/编辑角色信息
let create = reactive({
  id: 0,
  name: "",
  description: "",
  permissions: []
})
// 挂载数据，初始化数据
onMounted(() => {
  getRoleList()
  getPermissionTree()
})
// 获取用户角色列表
const getRoleList = async () => {
  const response = await http.roleApi.getRoleList(pageConfig)
  if (response.status === 200) {
    pageConfig.total = response.data.total
    roleList.value = response.data.data
  }
}
// 获取权限树
const getPermissionTree = async () => {
  const response = await http.roleApi.getPermissions()
  if (response.status === 200) {
    permissionTree.value = response.data
  }
}
// 新建用户表单校验
const formDataRules = reactive({
  name: [
    {required: true, message: '请输入角色名称', trigger: 'blur'},
    {max: 10, message: '角色名称不得超过10个字符', trigger: 'blur'},
  ],
  description: [
    {required: false, message: '请输入角色描述', trigger: 'blur'},
    {max: 20, message: '角色描述不得超过255个字符', trigger: 'blur'},
  ]
})

let createDialog = ref(false)
const formDataRef = ref()

// 点击添加按钮
function ClickAdd() {
  isEdit.value = false
  // 重置表单数据
  Object.assign(create, {
    id: 0,
    name: "",
    description: "",
    permissions: []
  })
  createDialog.value = true
  nextTick(() => {
    if (permTreeRef.value) {
      permTreeRef.value.setCheckedKeys([])
    }
  })
}

// 点击编辑按钮
function EditDialog(row) {
  isEdit.value = true
  createDialog.value = true
  nextTick(() => {
    create.id = row.id
    create.name = row.name
    create.description = row.description
    create.permissions = row.permissions || []
    if (permTreeRef.value) {
      permTreeRef.value.setCheckedKeys(create.permissions)
    }
  })
}

// 保存角色（新建/编辑统一入口）
async function saveRole() {
  const valid = await formDataRef.value.validate().catch(() => false)
  if (!valid) return
  // 收集树中选中的权限
  const checkedKeys = permTreeRef.value ? permTreeRef.value.getCheckedKeys(true) : []
  const payload = {
    name: create.name,
    description: create.description,
    permissions: checkedKeys
  }
  if (isEdit.value) {
    const res = await http.roleApi.updateRole(create.id, payload)
    if (res.status === 200) {
      createDialog.value = false
      ElNotification({
        type: 'success',
        title: '已成功修改角色！',
        duration: 1500,
      })
      await getRoleList()
    } else {
      ElNotification({
        title: '修改角色失败！',
        message: res.data.detail,
        type: 'error',
        duration: 1500
      })
    }
  } else {
    const response = await http.roleApi.createRole(payload)
    if (response.status === 201) {
      createDialog.value = false
      ElNotification({
        type: 'success',
        title: '已成功新建角色！',
        duration: 1500,
      })
      await getRoleList()
    } else {
      ElNotification({
        title: '新建角色失败！',
        message: response.data.detail,
        type: 'error',
        duration: 1500
      })
    }
  }
}

// 删除用户
async function deleteRole(id) {
  ElMessageBox.confirm(
      '此操作不可恢复，确认删除该角色吗？',
      '提示', {
        confirmButtonText: '确认',
        cancelButtonText: '取消',
        center: true,
        type: 'warning'
      })
      .then(async () => {
        const response = await http.roleApi.deleteRole(id)
        if (response.status === 204) {
          await getRoleList()
          ElNotification({
            type: 'success',
            title: '角色删除成功！',
            duration: 1500
          })
        } else {
          ElNotification({
            title: '角色删除失败！',
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
