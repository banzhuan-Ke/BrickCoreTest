<template>
  <div
    ref="pageRef"
    class="mian mian--cursor-fx"
    :class="{ 'theme-pro-page': uStore.uiTheme === 'pro' }"
  >
    <div class="login-bg-base" :style="pageBgStyle" aria-hidden="true" />
    <LoginBgEffects :container="pageRef" :motion-config="pageConfig" />
    <div class="login-theme-bar">
      <ThemeSwitcher />
      <el-tooltip
        v-if="uStore.uiTheme === 'classic'"
        :content="uStore.darkMode ? '切换到浅色模式' : '切换到暗黑模式'"
        placement="bottom"
      >
        <el-button
          circle
          @click="uStore.toggleDarkMode"
          :icon="uStore.darkMode ? 'Moon' : 'Sunny'"
          class="dark-toggle"
        />
      </el-tooltip>
    </div>
    <div class="login_shell">
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
      <div class="login_box">
        <div class="form-panel">
          <h3 class="form-panel__title">账号登录</h3>
          <p class="form-panel__subtitle">{{ pageConfig.welcome_title }}</p>
        </div>
      <div class="login-form">
        <el-form :model="loginForm" :rules="loginRules" ref="loginFormRef">
          <el-form-item prop="username" @keyup.enter="loginSubmit(loginFormRef)">
            <el-input 
              prefix-icon="UserFilled" 
              v-model="loginForm.username" 
              autocomplete="off" 
              placeholder="请输入账号"
              clearable/>
          </el-form-item>
          <el-form-item prop="password" @keyup.enter="loginSubmit(loginFormRef)">
            <el-input 
              prefix-icon="Lock" 
              :type="showPassword ? 'text' : 'password'" 
              v-model="loginForm.password"
              autocomplete="off" 
              placeholder="请输入密码" 
              clearable>
              <template #suffix>
                <el-icon @click="showPassword = !showPassword" style="cursor: pointer;">
                  <component :is="showPassword ? 'View':'Hide' "/>
                </el-icon>
              </template>
            </el-input>
          </el-form-item>
          <div class="remember-row">
            <el-switch v-model="loginForm.status" inactive-text="记住密码"/>
          </div>
          <div class="action-buttons">
            <el-button @click='resetForm(loginFormRef)' icon="CircleClose">重置</el-button>
            <el-button :disabled='isClick' type="primary" @click="loginSubmit(loginFormRef)" icon="Avatar">
              登录
            </el-button>
          </div>
          <div v-if="pageConfig.show_register" class="register-link">
            <el-link type="primary" @click="router.push('/register')">还没有账号？立即注册</el-link>
          </div>
        </el-form>
      </div>
      </div>
    </div>
    <div class="login-footer">
      <span>{{ pageConfig.footer_text }}</span>
    </div>
  </div>
</template>

<script setup>
import {ElNotification, ElMessage} from 'element-plus'
import {ref, reactive, computed, onMounted, watch} from 'vue'
import http from '@/api/index'
import {UserStore} from '@/stores/module/UserStore'
import { resetMenuExpandedSession } from '@/datas/Menu'
import {ProjectStore} from '@/stores/module/ProjectStore'
import {useRouter, useRoute} from 'vue-router'
import ThemeSwitcher from '@/components/ThemeSwitcher.vue'
import LoginBgEffects from '@/components/LoginBgEffects.vue'

const pageRef = ref(null)
import { useLoginPageConfig } from '@/composables/useLoginPageConfig.js'
import { LOGIN_PAGE_DEFAULTS } from '@/constants/loginPageBackgrounds.js'
import { LOGIN_HIGHLIGHTS } from '@/constants/loginHighlights.js'

const highlights = LOGIN_HIGHLIGHTS

const { loadLoginPageConfig, getBackgroundStyle } = useLoginPageConfig()
const pageConfig = reactive({ ...LOGIN_PAGE_DEFAULTS })
const pageBgStyle = ref({})

async function refreshPageLook() {
  const cfg = await loadLoginPageConfig()
  Object.assign(pageConfig, cfg)
  pageBgStyle.value = getBackgroundStyle(cfg)
}

// 创建用户状态管理
const uStore = UserStore()
const proStore = ProjectStore()
// 创建路由
const router = useRouter()
const route = useRoute()
// 定义登录的表单数据
const loginForm = reactive({
  username: "",
  password: "",
  status: true
})
// 定义密码是否显示
const showPassword = ref(false)

// 定义表单的验证对象和规则
const loginFormRef = ref()
// 定义表单的验证规则
const loginRules = reactive({
  username: [
    {required: true, message: '账号不能为空！', trigger: 'blur'},
    {min: 2, max: 18, message: '账号必须在2-18位之间！', trigger: 'blur'},
  ],
  password: [
    {required: true, message: '密码不能为空！', trigger: 'blur'},
    {min: 6, max: 18, message: '密码必须在6-18位之间！', trigger: 'blur'},
  ],
})

// 定义登录的方法
function loginSubmit(elForm) {
  // 进行表单预先校验
  elForm.validate(async function (res) {
    if (!res) return
    // 参数校验通过
    try {
      const response = await http.userApi.LoginApi(loginForm)
      if (response.status === 200) {
        ElNotification({
          title: '登录成功',
          message: '欢迎登录 BrickCore！',
          type: 'success',
          duration: 1500,
        })
        uStore.token = response.data.token
        uStore.username = loginForm.username
        uStore.userInfo = response.data.user
        uStore.permissions = response.data.user.permissions || []
        if (response.data.user?.default_project_id) {
          uStore.userInfo.default_project_id = response.data.user.default_project_id
        }
        if (loginForm.status) {
          uStore.isAuthenticated = true
          // 本地持久化保存
          localStorage.setItem('remember', 'true')
          localStorage.setItem('username', loginForm.username)
          localStorage.setItem('password', loginForm.password)
        } else {
          localStorage.removeItem('remember')
          localStorage.removeItem('username')
          localStorage.removeItem('password')
        }
        // 清理旧标签和旧项目状态，确保每次登录都是全新会话
        resetMenuExpandedSession()
        uStore.clearAllTabs()
        proStore.$reset()
        localStorage.removeItem('projectStore')
        const defaultProjectId = response.data.user?.default_project_id
        if (defaultProjectId) {
          try {
            const proRes = await http.projectApi.getDetail(defaultProjectId)
            if (proRes.status === 200 && proRes.data?.id) {
              await proStore.applyProject(proRes.data)
              await router.push({ name: 'dashboard' })
              return
            }
          } catch (e) {
            console.warn('默认项目加载失败', e)
          }
        }
        await router.push({ name: 'projectList' })
      } else {
        ElNotification({
          title: '登录失败！',
          message: response.data.detail || '未知错误',
          type: 'error',
          duration: 1500,
        })
      }
    } catch (error) {
      // axios 拦截器对非 2xx 状态码会 reject，在这里统一处理
      const detail = error?.data?.detail || error?.response?.data?.detail || '网络异常或服务器错误'
      ElNotification({
        title: '登录失败！',
        message: detail,
        type: 'error',
        duration: 1500,
      })
    }
  })
}

// 重置表单的方法
function resetForm(elForm) {
  if (!elForm) return
  elForm.resetFields()
}

// 当账号密码为空时，禁止点击登录按钮
const isClick = computed(() => {
  return !(loginForm.username !== '' && loginForm.password !== '')
})

// 页面加载时，判断是否记住密码，如果记住密码，则自动填充账号和密码
onMounted(async () => {
  await refreshPageLook()
  if (route.query.msg === 'no_permission') {
    ElMessage.warning('当前账号权限不足，请联系管理员分配权限')
  }
  if (localStorage.getItem('remember') === 'true') {
    loginForm.username = localStorage.getItem('username') || ''
    loginForm.password = localStorage.getItem('password') || ''
    loginForm.status = true
  }
})

watch(() => uStore.uiTheme, () => {
  pageBgStyle.value = getBackgroundStyle(pageConfig)
})
</script>

<style scoped lang="scss">
@use './Login.scss';
</style>
