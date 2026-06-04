<template>
  <div class="profile-page">
    <el-row :gutter="20">
      <!-- 左侧头像卡片 -->
      <el-col :xs="24" :sm="8" :md="6">
        <el-card class="avatar-card" shadow="hover">
          <div class="avatar-wrapper">
            <el-avatar :size="120" :src="avatarUrl" fit="cover">
              <el-icon :size="60"><UserFilled /></el-icon>
            </el-avatar>
            <el-upload
              class="avatar-uploader"
              action=""
              :show-file-list="false"
              :before-upload="beforeAvatarUpload"
              :http-request="handleAvatarUpload"
              accept="image/jpeg,image/png,image/gif,image/webp"
            >
              <el-button type="primary" text size="small" :loading="uploading">
                <el-icon><Camera /></el-icon>
                更换头像
              </el-button>
            </el-upload>
          </div>
          <div class="user-name">{{ form.nickname || userStore.userInfo?.username }}</div>
          <div class="user-role">
            <el-tag v-if="userStore.userInfo?.is_superuser" type="primary">超级管理员</el-tag>
            <el-tag v-else type="info">普通用户</el-tag>
          </div>
          <div class="user-meta">
            <div><el-icon><User /></el-icon> {{ userStore.userInfo?.username }}</div>
            <div><el-icon><Message /></el-icon> {{ form.email || '未设置邮箱' }}</div>
            <div><el-icon><Phone /></el-icon> {{ form.mobile || '未设置手机号' }}</div>
          </div>
        </el-card>
      </el-col>

      <!-- 右侧信息卡片 -->
      <el-col :xs="24" :sm="16" :md="18">
        <el-card shadow="hover">
          <el-tabs v-model="activeTab">
            <!-- 基本资料 -->
            <el-tab-pane label="基本资料" name="info">
              <el-form
                ref="infoFormRef"
                :model="form"
                :rules="infoRules"
                label-width="100px"
                class="profile-form"
              >
                <el-form-item label="登录名">
                  <el-input v-model="form.username" disabled />
                </el-form-item>
                <el-form-item label="用户昵称" prop="nickname">
                  <el-input v-model="form.nickname" placeholder="请输入用户昵称" maxlength="50" show-word-limit />
                </el-form-item>
                <el-form-item label="邮箱" prop="email">
                  <el-input v-model="form.email" placeholder="请输入邮箱地址" />
                </el-form-item>
                <el-form-item label="手机号" prop="mobile">
                  <el-input v-model="form.mobile" placeholder="请输入手机号" maxlength="11" />
                </el-form-item>
                <el-form-item>
                  <el-button type="primary" @click="saveProfile" :loading="saving">
                    保存资料
                  </el-button>
                  <el-button @click="resetForm">重置</el-button>
                </el-form-item>
              </el-form>
            </el-tab-pane>

            <!-- 修改密码 -->
            <el-tab-pane label="修改密码" name="password">
              <el-form
                ref="pwdFormRef"
                :model="pwdForm"
                :rules="pwdRules"
                label-width="100px"
                class="profile-form"
              >
                <el-form-item label="原密码" prop="old_password">
                  <el-input
                    v-model="pwdForm.old_password"
                    type="password"
                    placeholder="请输入原密码"
                    show-password
                  />
                </el-form-item>
                <el-form-item label="新密码" prop="new_password">
                  <el-input
                    v-model="pwdForm.new_password"
                    type="password"
                    placeholder="请输入新密码（不少于6位）"
                    show-password
                  />
                </el-form-item>
                <el-form-item label="确认密码" prop="new_password_confirm">
                  <el-input
                    v-model="pwdForm.new_password_confirm"
                    type="password"
                    placeholder="请再次输入新密码"
                    show-password
                  />
                </el-form-item>
                <el-form-item>
                  <el-button type="primary" @click="savePassword" :loading="pwdSaving">
                    修改密码
                  </el-button>
                  <el-button @click="resetPwdForm">重置</el-button>
                </el-form-item>
              </el-form>
            </el-tab-pane>
          </el-tabs>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { UserStore } from '@/stores/module/UserStore'
import { userApi, fileApi } from '@/api/modules/sys'
import { useRouter } from 'vue-router'

const userStore = UserStore()
const router = useRouter()

const activeTab = ref('info')
const saving = ref(false)
const pwdSaving = ref(false)
const uploading = ref(false)

const infoFormRef = ref()
const pwdFormRef = ref()

// 头像URL处理
const avatarUrl = computed(() => {
  const avatar = form.avatar
  if (!avatar) return ''
  if (avatar.startsWith('http')) return avatar
  // 使用 VITE_BASE_API 的 origin 拼接，确保开发/生产环境都能正确访问
  const baseAPI = import.meta.env.VITE_BASE_API || ''
  try {
    const url = new URL(baseAPI, window.location.href)
    return `${url.origin}${avatar}`
  } catch {
    return `${window.location.origin}${avatar}`
  }
})

// 基本资料表单
const form = reactive({
  username: '',
  nickname: '',
  email: '',
  mobile: '',
  avatar: ''
})

const infoRules = {
  nickname: [
    { required: true, message: '请输入用户昵称', trigger: 'blur' },
    { max: 50, message: '昵称长度不超过50个字符', trigger: 'blur' }
  ],
  email: [
    { required: true, message: '请输入邮箱地址', trigger: 'blur' },
    { type: 'email', message: '邮箱格式不正确', trigger: 'blur' }
  ],
  mobile: [
    { required: true, message: '请输入手机号', trigger: 'blur' },
    { pattern: /^1[3-9]\d{9}$/, message: '手机号格式不正确', trigger: 'blur' }
  ]
}

// 密码表单
const pwdForm = reactive({
  old_password: '',
  new_password: '',
  new_password_confirm: ''
})

const validateConfirmPwd = (rule, value, callback) => {
  if (value !== pwdForm.new_password) {
    callback(new Error('两次输入的密码不一致'))
  } else {
    callback()
  }
}

const pwdRules = {
  old_password: [
    { required: true, message: '请输入原密码', trigger: 'blur' }
  ],
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, message: '密码长度不能少于6位', trigger: 'blur' }
  ],
  new_password_confirm: [
    { required: true, message: '请再次输入新密码', trigger: 'blur' },
    { validator: validateConfirmPwd, trigger: 'blur' }
  ]
}

// 加载用户信息
const loadProfile = async () => {
  try {
    const res = await userApi.getProfile()
    const data = res.data
    if (data) {
      form.username = data.username || ''
      form.nickname = data.nickname || ''
      form.email = data.email || ''
      form.mobile = data.mobile || ''
      form.avatar = data.avatar || ''
      // 同步更新 store
      userStore.userInfo = { ...userStore.userInfo, ...data }
    }
  } catch (error) {
    console.error('获取用户信息失败:', error)
    // 如果接口失败，回退到 store 中的数据
    const u = userStore.userInfo || {}
    form.username = u.username || ''
    form.nickname = u.nickname || ''
    form.email = u.email || ''
    form.mobile = u.mobile || ''
    form.avatar = u.avatar || ''
  }
}

// 保存资料
const saveProfile = async () => {
  const valid = await infoFormRef.value.validate().catch(() => false)
  if (!valid) return

  saving.value = true
  try {
    const res = await userApi.updateProfile({
      nickname: form.nickname,
      email: form.email,
      mobile: form.mobile,
      avatar: form.avatar
    })
    ElMessage.success('资料保存成功')
    // 同步更新 store
    if (res.data) {
      userStore.userInfo = { ...userStore.userInfo, ...res.data }
    }
  } catch (error) {
    const msg = error.response?.data?.detail || '保存失败'
    ElMessage.error(msg)
  } finally {
    saving.value = false
  }
}

// 保存密码
const savePassword = async () => {
  const valid = await pwdFormRef.value.validate().catch(() => false)
  if (!valid) return

  pwdSaving.value = true
  try {
    await userApi.changePassword({
      old_password: pwdForm.old_password,
      new_password: pwdForm.new_password,
      new_password_confirm: pwdForm.new_password_confirm
    })
    ElMessage.success('密码修改成功，请重新登录')
    resetPwdForm()
    // 延迟登出，让用户看到提示
    setTimeout(() => {
      userStore.clearSession()
      localStorage.removeItem('userInfo')
      localStorage.removeItem('projectStore')
      router.push({ name: 'login' })
    }, 1500)
  } catch (error) {
    const msg = error.response?.data?.detail || '密码修改失败'
    ElMessage.error(msg)
  } finally {
    pwdSaving.value = false
  }
}

// 头像上传前校验
const beforeAvatarUpload = (rawFile) => {
  const allowed = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
  if (!allowed.includes(rawFile.type)) {
    ElMessage.error('仅支持 jpg/png/gif/webp 格式的图片')
    return false
  }
  if (rawFile.size / 1024 / 1024 > 2) {
    ElMessage.error('图片大小不能超过 2MB')
    return false
  }
  return true
}

// 自定义上传头像
const handleAvatarUpload = async ({ file }) => {
  uploading.value = true
  try {
    const url = await fileApi.uploadAvatar(file)
    if (url) {
      form.avatar = url
      // 同步更新 store
      userStore.userInfo = { ...userStore.userInfo, avatar: url }
      ElMessage.success('头像上传成功')
      // 同时触发保存，将头像更新到数据库
      await userApi.updateProfile({
        nickname: form.nickname,
        email: form.email,
        mobile: form.mobile,
        avatar: url
      })
    }
  } catch (error) {
    const msg = error.response?.data?.detail || '头像上传失败'
    ElMessage.error(msg)
  } finally {
    uploading.value = false
  }
}

const resetForm = () => {
  loadProfile()
}

const resetPwdForm = () => {
  pwdForm.old_password = ''
  pwdForm.new_password = ''
  pwdForm.new_password_confirm = ''
  pwdFormRef.value?.resetFields()
}

onMounted(() => {
  loadProfile()
})
</script>

<style scoped lang="scss">
.profile-page {
  padding: 20px;
  max-width: 1200px;
  margin: 0 auto;
}

.avatar-card {
  text-align: center;
  .avatar-wrapper {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 12px;
    margin-bottom: 16px;
  }
  .user-name {
    font-size: 18px;
    font-weight: bold;
    margin-bottom: 8px;
  }
  .user-role {
    margin-bottom: 16px;
  }
  .user-meta {
    text-align: left;
    font-size: 14px;
    color: #606266;
    div {
      display: flex;
      align-items: center;
      gap: 6px;
      margin-bottom: 8px;
      .el-icon {
        color: #909399;
      }
    }
  }
}

.profile-form {
  max-width: 500px;
  padding-top: 10px;
}
</style>
