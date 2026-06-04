<template>
  <router-view/>
</template>

<script setup>
import {reactive, watch} from 'vue'
import http from '@/api/index'
import {UserStore, readUiThemeFromStorage} from '@/stores/module/UserStore'
import {RouterView} from 'vue-router'

const uStore = UserStore()

// 持久化插件 rehydrate 后，以独立 uiTheme 键为准（避免旧 userInfo 覆盖）
uStore.uiTheme = readUiThemeFromStorage()

// 同步界面风格与暗黑模式
watch(
  () => [uStore.uiTheme, uStore.darkMode],
  () => uStore.syncThemeToDocument(),
  { immediate: true }
)

// 字体样式
const font = reactive({
  color: 'rgba(0,0,0,0.15)',
  fontSize: 20,
  fontWeight: 'normal',
  rotate: -45,
})

// 定时校验token是否有效
setInterval(async () => {
  // 每隔半小时校验用户的token是否有效
  const response = await http.userApi.verifyToken({
    'token': uStore.token
  })
  uStore.isAuthenticated = response.status !== 200
}, 1000 * 60 * 30)
</script>

<style scoped>
</style>
