<template>
  <div class="box">
    <div class="tabs">
      <div class="button-wrapper">
        <el-dropdown v-if="uStore.tabs.length > 0" trigger="click" @command="onBulkCommand">
          <el-button type="danger" size="small">
            关闭
            <el-icon class="el-icon--right"><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="others" :disabled="uStore.tabs.length <= 1">关闭其他</el-dropdown-item>
              <el-dropdown-item command="all" divided>全部关闭</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
      <div class="tabs-area" ref="tabsAreaRef" @contextmenu.prevent="onAreaContextMenu">
        <el-tabs
          :model-value="route.path"
          type="card"
          class="nav-tabs"
          @tab-click="clickTab"
          @tab-remove="clickDelete"
        >
          <el-tab-pane
            v-for="i in uStore.tabs"
            :key="i.path"
            :name="i.path"
            :closable="uStore.tabs.length > 1"
          >
            <template #label>
              <span
                class="tab-label"
                @contextmenu.prevent.stop="onTabContextMenu($event, i.path)"
              >
                <el-icon :size="15" class="tab-icon">
                  <component :is="i.icon" />
                </el-icon>
                <span class="tab-text">{{ i.name }}</span>
              </span>
            </template>
          </el-tab-pane>
        </el-tabs>
      </div>
    </div>

    <ul
      v-show="ctx.visible"
      class="tab-ctx-menu"
      :style="{ left: `${ctx.x}px`, top: `${ctx.y}px` }"
      @click.stop
    >
      <li @click="runCtx('current')">关闭当前</li>
      <li :class="{ disabled: uStore.tabs.length <= 1 }" @click="runCtx('others')">关闭其他</li>
      <li :class="{ disabled: !canCloseLeft }" @click="runCtx('left')">关闭左侧</li>
      <li :class="{ disabled: !canCloseRight }" @click="runCtx('right')">关闭右侧</li>
      <li class="divider" />
      <li @click="runCtx('all')">全部关闭</li>
    </ul>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import Sortable from 'sortablejs'
import { ArrowDown } from '@element-plus/icons-vue'
import { UserStore } from '@/stores/module/UserStore'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox, ElNotification } from 'element-plus'

const route = useRoute()
const router = useRouter()
const uStore = UserStore()
const tabsAreaRef = ref(null)
let sortableInstance = null

const ctx = reactive({
  visible: false,
  x: 0,
  y: 0,
  path: '',
})

const ctxIndex = computed(() => uStore.tabs.findIndex((t) => t.path === ctx.path))
const canCloseLeft = computed(() => ctxIndex.value > 0)
const canCloseRight = computed(() => ctxIndex.value >= 0 && ctxIndex.value < uStore.tabs.length - 1)

function initSortable() {
  sortableInstance?.destroy()
  sortableInstance = null

  const nav = tabsAreaRef.value?.querySelector('.el-tabs__nav')
  if (!nav || uStore.tabs.length < 2) return

  sortableInstance = Sortable.create(nav, {
    animation: 150,
    draggable: '.el-tabs__item',
    filter: '.is-icon-close',
    preventOnFilter: true,
    ghostClass: 'tab-drag-ghost',
    onEnd({ oldIndex, newIndex }) {
      if (oldIndex == null || newIndex == null || oldIndex === newIndex) return
      uStore.reorderTabs(oldIndex, newIndex)
      nextTick(initSortable)
    },
  })
}

function hideCtx() {
  ctx.visible = false
}

function onTabContextMenu(e, path) {
  ctx.path = path
  ctx.x = e.clientX
  ctx.y = e.clientY
  ctx.visible = true
}

function onAreaContextMenu(e) {
  ctx.path = route.path
  ctx.x = e.clientX
  ctx.y = e.clientY
  ctx.visible = true
}

function navigateAfterClose(removedPath) {
  if (route.path !== removedPath) return
  const tabs = uStore.tabs
  if (!tabs.length) {
    router.push('/dashboard')
    return
  }
  router.push(tabs[tabs.length - 1].path)
}

function confirmCloseAll() {
  return ElMessageBox.confirm('确定要关闭所有标签吗？将回到首页看板。', '提示', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning',
    center: true,
  })
}

async function runCtx(action) {
  const path = ctx.path || route.path
  hideCtx()
  if (action === 'current') {
    if (uStore.tabs.length <= 1) {
      ElMessage.info('至少保留一个页签')
      return
    }
    uStore.deleteTabs(path)
    navigateAfterClose(path)
    return
  }
  if (action === 'others') {
    uStore.closeOtherTabs(path)
    if (route.path !== path) router.push(path)
    return
  }
  if (action === 'left') {
    if (!canCloseLeft.value) return
    const current = route.path
    uStore.closeLeftTabs(path)
    if (!uStore.tabs.some((t) => t.path === current)) {
      router.push(path)
    }
    return
  }
  if (action === 'right') {
    if (!canCloseRight.value) return
    const current = route.path
    uStore.closeRightTabs(path)
    if (!uStore.tabs.some((t) => t.path === current)) {
      router.push(path)
    }
    return
  }
  if (action === 'all') {
    try {
      await confirmCloseAll()
      uStore.clearAllTabs()
      ElNotification({ title: '已关闭所有标签', type: 'success', duration: 1500 })
      await router.push('/dashboard')
    } catch {
      ElMessage({ type: 'info', message: '已取消关闭操作。', duration: 1500 })
    }
  }
}

async function onBulkCommand(cmd) {
  if (cmd === 'others') {
    uStore.closeOtherTabs(route.path)
    return
  }
  if (cmd === 'all') {
    try {
      await confirmCloseAll()
      uStore.clearAllTabs()
      ElNotification({ title: '已关闭所有标签', type: 'success', duration: 1500 })
      await router.push('/dashboard')
    } catch {
      ElMessage({ type: 'info', message: '已取消关闭操作。', duration: 1500 })
    }
  }
}

onMounted(() => {
  nextTick(initSortable)
  document.addEventListener('click', hideCtx)
  document.addEventListener('scroll', hideCtx, true)
})
watch(() => uStore.tabs.length, () => nextTick(initSortable))
onBeforeUnmount(() => {
  sortableInstance?.destroy()
  document.removeEventListener('click', hideCtx)
  document.removeEventListener('scroll', hideCtx, true)
})

function clickTab(ele) {
  router.push(ele.props.name)
}

function clickDelete(item) {
  if (uStore.tabs.length <= 1) {
    ElMessage.info('至少保留一个页签')
    return
  }
  uStore.deleteTabs(item)
  navigateAfterClose(item)
}
</script>

<style scoped lang="scss">
@use "./Tab.scss";
</style>
