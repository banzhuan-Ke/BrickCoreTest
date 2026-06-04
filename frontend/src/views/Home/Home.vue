<template>
  <el-container>
    <!-- 左侧侧边栏 -->
    <el-aside :style="{width:uStore.isCollapse? '65px':'200px',height:'100vh'}">
      <Menu></Menu>
    </el-aside>
    <el-container>
      <!-- 页面头部内容 -->
      <el-header>
        <Header></Header>
      </el-header>
      <!-- 页面主体内容 -->
      <el-main>
        <!-- 标签栏 -->
        <Tabs></Tabs>
        <!-- 主体内容区域 -->
        <div class="main_box">
          <router-view></router-view>
        </div>
      </el-main>
      <!-- 页面底部内容 -->
      <el-footer>
        <Footer></Footer>
      </el-footer>
    </el-container>
    <PlatformAssistant />
  </el-container>
</template>

<script setup>
import Menu from './components/Menu.vue'
import Footer from './components/Footer.vue'
import Header from './components/Header.vue'
import Tabs from './components/Tab.vue'
import PlatformAssistant from '@/components/PlatformAssistant.vue'
import {UserStore} from '@/stores/module/UserStore'
import {RouterView} from 'vue-router'

const uStore = UserStore()
</script>

<style scoped lang="scss">
@use "./Home.scss";
</style>