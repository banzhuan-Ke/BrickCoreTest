<template>
  <div
    ref="pageRef"
    class="mian mian--cursor-fx"
    :class="{ 'theme-pro-page': uStore.uiTheme === 'pro' }"
  >
    <div class="login-bg-base" :style="pageBgStyle" aria-hidden="true" />
    <LoginBgEffects :container="pageRef" :motion-config="loginPageConfig" />
    <div class="login_shell login_shell--register">
      <aside class="login_highlights">
        <img src="@/assets/images/brickcore-mark.svg" class="highlights-logo" alt="BrickCore">
        <p class="highlights-welcome">{{ highlights.welcome }}</p>
        <h2 class="highlights-brand">{{ highlights.brandName }}</h2>
        <p class="highlights-tagline">{{ highlights.tagline }}</p>
        <ul class="highlights-list">
          <li v-for="item in highlights.items" :key="item.title">
            <span class="highlights-check"><el-icon><CircleCheckFilled /></el-icon></span>
            <div>
              <b>{{ item.title }}</b>
              <span>{{ item.desc }}</span>
            </div>
          </li>
        </ul>
      </aside>
      <div class="register_box">
        <div class="form-panel">
          <h3 class="form-panel__title">账号注册</h3>
          <p class="form-panel__subtitle">填写信息完成注册</p>
        </div>
      <div class="register-form">
        <el-form :model="registerFrom" :rules="registerRules" ref="registerFormRef">
          <el-form-item prop="username">
            <el-input 
              prefix-icon="UserFilled" 
              v-model="registerFrom.username"
              autocomplete="off" 
              placeholder="请输入用户名" 
              clearable/>
          </el-form-item>
          <el-form-item prop="password">
            <el-input 
              prefix-icon="Lock" 
              :type="showPassword1 ? 'text' : 'password'" 
              v-model="registerFrom.password"
              autocomplete="off" 
              placeholder="请输入密码" 
              clearable>
              <template #suffix>
                <el-icon @click="showPassword1 = !showPassword1" style="cursor: pointer;">
                  <component :is="showPassword1 ? 'View':'Hide' "/>
                </el-icon>
              </template>
            </el-input>
          </el-form-item>
          <el-form-item prop="password_confirm">
            <el-input 
              prefix-icon="Lock" 
              :type="showPassword2 ? 'text' : 'password'" 
              v-model="registerFrom.password_confirm"
              autocomplete="off" 
              placeholder="再次确认密码" 
              clearable>
              <template #suffix>
                <el-icon @click="showPassword2 = !showPassword2" style="cursor: pointer;">
                  <component :is="showPassword2 ? 'View':'Hide' "/>
                </el-icon>
              </template>
            </el-input>
          </el-form-item>
          <el-form-item prop="nickname">
            <el-input 
              prefix-icon="Avatar" 
              v-model="registerFrom.nickname"
              autocomplete="off" 
              placeholder="请输入用户昵称" 
              clearable/>
          </el-form-item>
          <el-form-item prop="mobile">
            <el-input 
              prefix-icon="Phone" 
              v-model="registerFrom.mobile"
              autocomplete="off" 
              placeholder="请输入手机号" 
              clearable/>
          </el-form-item>
          <el-form-item prop="email">
            <el-input 
              prefix-icon="Message" 
              v-model="registerFrom.email"
              autocomplete="off" 
              placeholder="请输入邮箱" 
              clearable/>
          </el-form-item>
          <el-form-item prop="admin_username">
            <el-input 
              prefix-icon="User" 
              v-model="registerFrom.admin_username"
              autocomplete="off" 
              placeholder="请输入超管账号（必填）" 
              clearable/>
          </el-form-item>
          <el-form-item prop="admin_password">
            <el-input 
              prefix-icon="Lock" 
              :type="showPassword3 ? 'text' : 'password'" 
              v-model="registerFrom.admin_password"
              autocomplete="off" 
              placeholder="请输入超管密码（必填）" 
              clearable>
              <template #suffix>
                <el-icon @click="showPassword3 = !showPassword3" style="cursor: pointer;">
                  <component :is="showPassword3 ? 'View':'Hide' "/>
                </el-icon>
              </template>
            </el-input>
          </el-form-item>
          <el-form-item prop="roles">
            <el-select 
              v-model="registerFrom.roles" 
              multiple 
              placeholder="请选择关联角色（可选）"
              clearable>
              <el-option v-for="role in roleList" :key="role.id" :label="role.name" :value="role.id"/>
            </el-select>
          </el-form-item>
          <div class="action-buttons">
            <el-button @click="resetForm(registerFormRef)" icon="CircleClose">
              重置
            </el-button>
            <el-button :disabled='isClick' type="primary" @click="registerSubmit(registerFormRef)" icon="CircleCheck">
              注册
            </el-button>
          </div>
          <div class="login-link">
            <el-link type="primary" @click="router.push('/login')">已有账号？立即登录</el-link>
          </div>
        </el-form>
      </div>
      </div>
    </div>
    <div class="login-footer">
      <span>{{ loginPageConfig.footer_text }}</span>
    </div>
  </div>
</template>

<script setup>
import {ElNotification} from 'element-plus'
import {ref, reactive, computed, onMounted, watch} from 'vue'
import http from '@/api/index'
import {useRouter} from 'vue-router'
import {UserStore} from '@/stores/module/UserStore'
import LoginBgEffects from '@/components/LoginBgEffects.vue'

const pageRef = ref(null)
import { useLoginPageConfig } from '@/composables/useLoginPageConfig.js'
import { LOGIN_PAGE_DEFAULTS } from '@/constants/loginPageBackgrounds.js'
import { REGISTER_HIGHLIGHTS } from '@/constants/loginHighlights.js'

const highlights = REGISTER_HIGHLIGHTS

const uStore = UserStore()
const { loadLoginPageConfig, getBackgroundStyle } = useLoginPageConfig()
const loginPageConfig = reactive({ ...LOGIN_PAGE_DEFAULTS })
const pageBgStyle = ref({})

async function refreshPageLook() {
  const cfg = await loadLoginPageConfig()
  Object.assign(loginPageConfig, cfg)
  pageBgStyle.value = getBackgroundStyle(cfg)
}

// 创建路由
const router = useRouter()
// 定义密码是否显示
const showPassword1 = ref(false)
const showPassword2 = ref(false)
const showPassword3 = ref(false)
// 登录的表单数据
const registerFrom = reactive({
  id: 0,
  username: "",
  password: "",
  password_confirm: "",
  email: "",
  mobile: "",
  nickname: "",
  is_superuser: false,
  roles: [],
  admin_username: "",
  admin_password: ""
})
// 分页数据
let pageConfig = reactive({
  page: 1,
  size: 10,
  total: 0
})
// 校验账号密码
const registerRules = reactive({
  username: [{required: true, message: '用户账号不能为空！', trigger: 'blur'}],
  password: [{required: true, message: '登录密码不能为空！', trigger: 'blur'}],
  password_confirm: [{required: true, message: '确认密码不能为空！', trigger: 'blur'}],
  nickname: [{required: true, message: '用户昵称不能为空！', trigger: 'blur'}],
  mobile: [{required: true, message: '手机号不能为空！', trigger: 'blur'}],
  email: [{required: true, message: '用户邮箱不能为空！', trigger: 'blur'}],
  admin_username: [{required: true, message: '超管账号不能为空！', trigger: 'blur'}],
  admin_password: [{required: true, message: '超管密码不能为空！', trigger: 'blur'}],
})

// 表单引用对象
const registerFormRef = ref()

// 提交注册的方法
function registerSubmit(elFrom) {
  // 进行表单预先校验
  elFrom.validate(async function (res) {
    if (!res) return
    const response = await http.userApi.RegisterApi(registerFrom)
    if (response.status === 201) {
      // 给出提示
      ElNotification({
        title: '用户注册成功！',
        message: `用户账号为：${registerFrom.username}`,
        type: 'success',
        duration: 1500
      })
      // 跳转到登录页
      router.push({name: 'login'})
    } else {
      ElNotification({
        title: '用户注册失败！',
        type: 'error',
        duration: 1500,
        message: response.data.detail
      })
    }
  })
}
// 获取角色列表方法
const roleList = ref([])

const getRoleList = async () => {
  const response = await http.roleApi.getRoleList(pageConfig)
  if (response.status === 200) {
    pageConfig.total = response.data.total
    roleList.value = response.data.data
  }
}
// 挂载数据，初始化数据
onMounted(async () => {
  await refreshPageLook()
  if (uStore.token) {
    await getRoleList().catch(() => {})
  }
})

watch(() => uStore.uiTheme, () => {
  pageBgStyle.value = getBackgroundStyle(loginPageConfig)
})
// 重置表单的方法
function resetForm(elForm) {
  if (!elForm) return
  elForm.resetFields()
}

// 当账号密码等为空时，禁止点击注册按钮
const isClick = computed(() => {
  return !(registerFrom.username !== '' && registerFrom.password !== '' && registerFrom.password_confirm !== '' && registerFrom.nickname !== '' && registerFrom.mobile !== '' && registerFrom.email !== '' && registerFrom.admin_username !== '' && registerFrom.admin_password !== '')
})
</script>

<style scoped lang="scss">
@use './Register.scss';
</style>
