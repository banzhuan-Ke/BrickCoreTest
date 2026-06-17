<template>
  <!-- 顶部的logo图标 -->
  <div class="logo">
    <img src="@/assets/images/brickcore-mark.svg" alt="BrickCore" class="logo-mark">
    <div class="title" v-if="!uStore.isCollapse">BrickCore</div>
  </div>
  <!-- 菜单 -->
  <el-menu :default-active="route.path" :collapse="uStore.isCollapse" collapse-transition size="large"
           class="menu-container">
    <template v-for="(group, groupIndex) in filteredMenuGroups" :key="group.title">
      <!-- 分组标题（展开时显示）-->
      <div v-if="!uStore.isCollapse" class="menu-group-header" @click="toggleGroup(groupIndex)">
        <div class="menu-group-title">
          <el-icon :size="16" class="group-icon">
            <component :is="group.icon"/>
          </el-icon>
          <span>{{ group.title }}</span>
        </div>
        <el-icon :size="14" class="expand-icon" :class="{ 'is-expanded': group.expanded }">
          <ArrowDown />
        </el-icon>
      </div>
      <!-- 菜单项 -->
      <div class="menu-items-wrapper" :class="{ 'is-collapsed': !group.expanded && !uStore.isCollapse }">
        <el-menu-item 
          :index="item.path" 
          v-for='item in group.items' 
          :key="item.path" 
          :disabled="proStore.isDisabled && !isMenuItemEnabled(item, group)"
          @click="MenuClick(item)">
          <el-icon :size="18" style="margin-right: 15px;">
            <component :is="item.icon"/>
          </el-icon>
          <span>{{ item.name }}</span>
        </el-menu-item>
      </div>
      <!-- 分组分隔线 -->
      <div v-if="!uStore.isCollapse && groupIndex < filteredMenuGroups.length - 1" class="menu-divider"></div>
    </template>
  </el-menu>
</template>

<script setup>
import {ProjectStore} from '@/stores/module/ProjectStore'
import {UserStore} from '@/stores/module/UserStore'
import {MenuGroups} from '@/datas/Menu'
import {useRoute, useRouter} from 'vue-router'
import {reactive, computed} from 'vue'

// 定义路由
const router = useRouter()
// 获取当前路由信息
const route = useRoute()
const proStore = ProjectStore()
const uStore = UserStore()

// 使用响应式数据管理菜单展开状态
const menuGroups = reactive(MenuGroups.map(g => ({
  ...g,
  expanded: g.expanded !== false
})))

// 根据权限过滤菜单分组和菜单项
const filteredMenuGroups = computed(() => {
  return menuGroups.map(group => {
    const items = group.items.filter(item => {
      if (item.anyPermissions?.length) {
        return item.anyPermissions.some((p) => uStore.hasPermission(p))
      }
      if (!item.permission) return true
      return uStore.hasPermission(item.permission)
    })
    return { ...group, items }
  }).filter(group => group.items.length > 0)
})

// 切换分组展开/收起
const toggleGroup = (index) => {
  menuGroups[index].expanded = !menuGroups[index].expanded
}

// 未选项目时仍可访问的菜单（如文档中心、项目管理、系统管理）
const isMenuItemEnabled = (item, group) => {
  if (item.noProjectRequired) return true
  if (item.path?.startsWith('/project')) return true
  if (group.title === '系统管理') return true
  return false
}

// 点击菜单项
const MenuClick = (item) => {
  if (item.external) {
    // 处理外部链接
    window.open(item.path)
  } else {
    // 内部路由正常跳转
    router.push(item.path)
  }
}
</script>

<style lang="scss" scoped>
@use './Menu.scss';
</style>
