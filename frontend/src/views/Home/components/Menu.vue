<template>
  <div class="logo">
    <img src="@/assets/images/brickcore-mark.svg" alt="BrickCore" class="logo-mark">
    <div class="title" v-if="!uStore.isCollapse">BrickCore</div>
  </div>
  <el-menu
    :default-active="activeMenuPath"
    :key="activeMenuPath"
    :collapse="uStore.isCollapse"
    collapse-transition
    class="menu-container"
  >
    <div
      v-for="group in filteredMenuGroups"
      :key="group.title"
      class="menu-group"
      :class="{
        'is-expanded': group.expanded && !uStore.isCollapse,
        'is-current': isGroupCurrent(group),
      }"
    >
      <button
        v-if="!uStore.isCollapse"
        type="button"
        class="menu-group-header"
        @click="toggleGroup(group.title)"
      >
        <span class="group-icon-wrap">
          <el-icon>
            <component :is="group.icon" />
          </el-icon>
        </span>
        <span class="group-label">{{ group.title }}</span>
        <el-icon class="group-chevron" :class="{ 'is-open': group.expanded }">
          <ArrowRight />
        </el-icon>
      </button>

      <div
        class="menu-group-panel"
        :class="{ 'is-collapsed': !group.expanded && !uStore.isCollapse }"
      >
        <el-menu-item
          v-for="item in group.items"
          :key="item.path"
          :index="item.path"
          :disabled="proStore.isDisabled && !isMenuItemEnabled(item, group)"
          @click="MenuClick(item)"
        >
          <span class="item-icon-wrap">
            <el-icon>
              <component :is="item.icon" />
            </el-icon>
          </span>
          <span>{{ item.name }}</span>
        </el-menu-item>
      </div>
    </div>
  </el-menu>
</template>

<script setup>
import { ArrowRight } from '@element-plus/icons-vue'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { UserStore } from '@/stores/module/UserStore'
import { MenuGroups } from '@/datas/Menu'
import { useRoute, useRouter } from 'vue-router'
import { computed, onMounted, ref, watch } from 'vue'
import { useCommunityEdition } from '@/composables/useCommunityEdition'

const MENU_EXPANDED_STORAGE_KEY = 'brickcore_menu_expanded_groups'

const router = useRouter()
const route = useRoute()
const proStore = ProjectStore()
const uStore = UserStore()
const { isCommunityEdition, loadCommunityEdition } = useCommunityEdition()

const expandedGroups = ref([])

function resolveMenuItemPath(path) {
  if (!path) return ''
  for (const group of MenuGroups) {
    for (const item of group.items) {
      if (item.external || !item.path) continue
      if (path === item.path || path.startsWith(`${item.path}/`)) {
        return item.path
      }
    }
  }
  return path
}

function resolveGroupTitleByPath(path) {
  if (!path) return ''
  for (const group of MenuGroups) {
    for (const item of group.items) {
      if (item.external || !item.path) continue
      if (path === item.path || path.startsWith(`${item.path}/`)) {
        return group.title
      }
    }
  }
  return MenuGroups[0]?.title || ''
}

function syncExpandedToRoute(path = route.path) {
  const title = resolveGroupTitleByPath(path)
  if (title) {
    expandedGroups.value = [title]
  }
}

function loadExpandedGroups() {
  syncExpandedToRoute(route.path)
}

function isGroupCurrent(group) {
  return group.items.some((item) => {
    if (item.external || !item.path) return false
    return route.path === item.path || route.path.startsWith(`${item.path}/`)
  })
}

onMounted(() => {
  loadCommunityEdition()
  loadExpandedGroups()
})

watch(
  () => route.path,
  (path) => {
    syncExpandedToRoute(path)
  }
)

const activeMenuPath = computed(() => resolveMenuItemPath(route.path))

watch(
  expandedGroups,
  (titles) => {
    localStorage.setItem(MENU_EXPANDED_STORAGE_KEY, JSON.stringify(titles))
  },
  { deep: true }
)

const filteredMenuGroups = computed(() => {
  return MenuGroups.map((group) => {
    const items = group.items.filter((item) => {
      if (isCommunityEdition.value && item.path === '/ai-qa-eval') {
        return false
      }
      if (item.anyPermissions?.length) {
        return item.anyPermissions.some((p) => uStore.hasPermission(p))
      }
      if (!item.permission) return true
      return uStore.hasPermission(item.permission)
    })
    return {
      ...group,
      items,
      expanded: expandedGroups.value.includes(group.title),
    }
  }).filter((group) => group.items.length > 0)
})

function toggleGroup(title) {
  if (expandedGroups.value.includes(title)) {
    expandedGroups.value = []
    return
  }
  expandedGroups.value = [title]
}

const isMenuItemEnabled = (item, group) => {
  if (item.noProjectRequired) return true
  if (item.path?.startsWith('/project')) return true
  if (group.title === '系统管理') return true
  return false
}

const MenuClick = (item) => {
  if (item.external) {
    window.open(item.path)
  } else {
    router.push(item.path)
  }
}
</script>

<style lang="scss" scoped>
@use './Menu.scss';
</style>
