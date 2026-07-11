<template>
  <div class="head_box">
    <!--左侧控制显示缩放-->
    <div class="left_box" v-if="!props.projectList">
      <el-tooltip class="box-item" effect="dark" content="展开/收起左侧菜单栏" placement="bottom">
        <div class="icon-btn">
          <el-icon :size="20" v-if='uStore.isCollapse' @click="switchCollapse">
            <Fold />
          </el-icon>
          <el-icon :size="20" v-else @click="switchCollapse">
            <Expand />
          </el-icon>
        </div>
      </el-tooltip>
    </div>
    <div class="left_box" v-else></div>
    
    <!-- 中间显示项目名称 -->
    <div class="center_box">
      <span v-if='proStore.projectInfo.name'>{{ proStore.projectInfo.name }}</span>
      <span v-else>请选择项目</span>
    </div>

    <div class="right_box">
      <el-tooltip content="项目内搜索 (Ctrl+K)" placement="bottom">
        <div class="icon-btn" @click="showSearch = true">
          <el-icon :size="20"><Search /></el-icon>
        </div>
      </el-tooltip>

      <!-- 界面风格 -->
      <el-tooltip content="切换界面风格" placement="bottom">
        <ThemeSwitcher compact />
      </el-tooltip>

      <!-- 暗黑模式（仅经典风格） -->
      <el-tooltip
        v-if="uStore.uiTheme === 'classic'"
        :content="uStore.darkMode ? '切换到浅色模式' : '切换到暗黑模式'"
        placement="bottom"
      >
        <div class="icon-btn" @click="uStore.toggleDarkMode">
          <el-icon :size="20">
            <component :is="uStore.darkMode ? 'Moon' : 'Sunny'" />
          </el-icon>
        </div>
      </el-tooltip>

      <!-- 帮助：快速弹窗 + 文档中心 -->
      <el-dropdown trigger="click" @command="onHelpCommand">
        <div class="icon-btn">
          <el-icon :size="20">
            <QuestionFilled />
          </el-icon>
        </div>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="quick">快速帮助</el-dropdown-item>
            <el-dropdown-item command="docs">文档中心（推荐）</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      
      <!--显示通知-->
      <el-badge :value="1" class="notice">
        <el-dropdown trigger="click">
          <div class="avatar">
            <el-icon style="vertical-align: middle" :size="20">
              <Bell/>
            </el-icon>
          </div>
          <template #dropdown>
            <el-dropdown-item>
              <img src="@/assets/images/qq.jpg" alt="qq" style="margin-top: 10px">
            </el-dropdown-item>
          </template>
        </el-dropdown>
      </el-badge>
      
      <!-- 显示时间 -->
      <div class="time_info">
        {{ nTime }}
      </div>
      
      <!-- 页面全屏展示 -->
      <div class="fullscreen">
        <el-tooltip class="box-item" effect="dark" content="开启/退出全屏模式" placement="bottom">
          <el-icon :size="20" v-if='!isFullscreen' @click="handleFullScreen">
            <FullScreen />
          </el-icon>
          <el-icon :size="20" v-else @click="handleFullScreen">
            <Minus />
          </el-icon>
        </el-tooltip>
      </div>
      
      <!---点击头像-->
      <div class="box">
        <el-dropdown trigger="click">
          <div style="display: flex; align-items: center; gap: 10px;">
            <div class="avatar">
              <img v-if="avatarUrl" :src="avatarUrl" alt="avatar" style="width: 100%; height: 100%; object-fit: cover; border-radius: 50%;">
              <img v-else src="@/assets/images/avatar.gif" alt="avatar">
            </div>
            <div class="username">{{ uStore.userInfo.nickname }}</div>
          </div>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click='goProfile' size="default" icon="User">个人中心</el-dropdown-item>
              <el-dropdown-item plain size="default" @click='logout' icon="SwitchButton">退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>
  </div>
  
  <!-- 使用帮助 -->
  <el-dialog
    v-model="showHelp"
    width="700px"
    append-to-body
    :fullscreen="isHelpFullscreen"
    destroy-on-close
    class="help-dialog"
  >
    <template #header>
      <div style="display: flex; justify-content: space-between; align-items: center;">
        <span style="font-size: 18px; font-weight: bold;">📖 BrickCore 使用说明</span>
        <el-button type="primary" text @click="toggleHelpFullscreen">
          <el-icon><FullScreen v-if="!isHelpFullscreen" /><Minus v-else /></el-icon>
          {{ isHelpFullscreen ? '退出全屏' : '全屏' }}
        </el-button>
      </div>
    </template>
    <HelpContent :is-help-fullscreen="isHelpFullscreen" />
  </el-dialog>

  <GlobalProjectSearch v-model="showSearch" />
</template>

<script setup>
import {ProjectStore} from "@/stores/module/ProjectStore"
import {UserStore} from '@/stores/module/UserStore'
import { resetMenuExpandedSession } from '@/datas/Menu'
import {useRouter} from 'vue-router'
import screenfull from "screenfull"
import {ref, onMounted, onBeforeUnmount, computed} from 'vue'
import {ElNotification, ElMessage, ElMessageBox} from 'element-plus'
import dateTools from "@/tools/dateTools.js"
import HelpContent from "@/components/HelpContent.vue"
import ThemeSwitcher from "@/components/ThemeSwitcher.vue"
import GlobalProjectSearch from "@/components/GlobalProjectSearch.vue"
import { Search } from '@element-plus/icons-vue'

// 定义props判断是否为项目列表页
const props = defineProps({
  projectList: false
})
const proStore = ProjectStore()
const uStore = UserStore()
const router = useRouter()

// 切换菜单折叠
const switchCollapse = () => {
  uStore.isCollapse = !uStore.isCollapse
}

// 退出登录
function logout() {
  ElMessageBox.confirm(
      "您是否确认退出登录?",
      "提示", {
        confirmButtonText: "确定",
        cancelButtonText: "取消",
        center: true,
        type: "warning"
      })
      .then(async () => {
        // 跳转到登录页面
        await router.push({name: 'login'})
        ElNotification({
          title: '已为您注销登录！',
          type: 'success',
          duration: 1500
        })
        // 彻底清理用户状态和项目状态（保留界面风格偏好）
        resetMenuExpandedSession()
        uStore.clearSession()
        proStore.$reset()
        localStorage.removeItem('projectStore')
        localStorage.removeItem('userInfo')
      })
      .catch(() => {
        ElMessage({
          type: 'info',
          message: '已取消退出登录操作。',
          duration: 1500
        })
      })
}

const showSearch = ref(false)

// 帮助对话框
let showHelp = ref(false)
let isHelpFullscreen = ref(false)

function toggleHelpFullscreen() {
  isHelpFullscreen.value = !isHelpFullscreen.value
}

// 头像URL
const avatarUrl = computed(() => {
  const avatar = uStore.userInfo?.avatar
  if (!avatar) return ''
  if (avatar.startsWith('http')) return avatar
  const baseAPI = import.meta.env.VITE_BASE_API || ''
  try {
    const url = new URL(baseAPI, window.location.href)
    return `${url.origin}${avatar}`
  } catch {
    return `${window.location.origin}${avatar}`
  }
})

function goProfile() {
  router.push('/profile')
}

function onHelpCommand(cmd) {
  if (cmd === 'docs') {
    router.push({ name: 'docsCenter', query: { doc: 'highlights' } })
    return
  }
  showHelp.value = true
}

// 顶部实时时间的显示
let nTime = ref()

// 获取当前时间 - 优化为 HH:mm 格式
function getNowTime() {
  let nowTime = new Date()
  let y = nowTime.getFullYear()
  let m = String(nowTime.getMonth() + 1).padStart(2, '0')
  let d = String(nowTime.getDate()).padStart(2, '0')
  let H = String(nowTime.getHours()).padStart(2, '0')
  let M = String(nowTime.getMinutes()).padStart(2, '0')
  return `${y}-${m}-${d} ${H}:${M}`
}

// 全屏
const isFullscreen = ref(screenfull.isFullscreen)
const onScreenfullChange = () => {
  isFullscreen.value = !!screenfull.isFullscreen
}

// 每隔一秒更新时间
let clockTimer = null
const onGlobalKeydown = (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault()
    showSearch.value = true
  }
}

onMounted(() => {
  nTime.value = getNowTime()
  clockTimer = setInterval(() => {
    nTime.value = getNowTime()
  }, 1000)
  if (screenfull.isEnabled) {
    screenfull.on('change', onScreenfullChange)
  }
  window.addEventListener('keydown', onGlobalKeydown)
})
onBeforeUnmount(() => {
  if (clockTimer) {
    clearInterval(clockTimer)
    clockTimer = null
  }
  if (screenfull.isEnabled) {
    screenfull.off('change', onScreenfullChange)
  }
  window.removeEventListener('keydown', onGlobalKeydown)
})
// 点击全屏
const handleFullScreen = () => {
  if (!screenfull.isEnabled) {
    ElNotification.error("您当前的浏览器不支持全屏！");
  } else {
    screenfull.toggle()
  }
}
</script>

<style scoped lang="scss">
@use "./Header.scss";
</style>
