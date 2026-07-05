<template>
  <div class="box">
    <div class="tabs">
      <!-- 关闭所有按钮 -->
      <div class="button-wrapper">
        <el-button type="danger" @click="clearAllTabs" v-if="uStore.tabs.length > 0">全部关闭</el-button>
      </div>
      <div class="tabs-area" ref="tabsAreaRef">
        <el-tabs icon="UserFilled" v-model='route.path' @tab-click="clickTab" @tab-remove='clickDelete'>
          <div v-for='i in uStore.tabs' :key="i.path">
            <el-tab-pane v-if='route.path !== i.path' :name="i.path" closable>
              <template #label>
                <el-icon :size="18" style="margin-right: 10px; vertical-align: middle;">
                  <component :is="i.icon" />
                </el-icon>
                <span>{{ i.name }}</span>
              </template>
            </el-tab-pane>
            <el-tab-pane v-else :name="i.path">
              <template #label>
                <el-icon :size="18" style="margin-right: 10px; vertical-align: middle;">
                  <component :is="i.icon" />
                </el-icon>
                <span>{{ i.name }}</span>
              </template>
            </el-tab-pane>
          </div>
        </el-tabs>
      </div>
    </div>
  </div>
</template>

<script setup>
import {onBeforeUnmount, onMounted, watch, nextTick, ref} from 'vue'
import Sortable from 'sortablejs'
import {UserStore} from '@/stores/module/UserStore'
import {useRoute, useRouter} from 'vue-router'
import {ElMessageBox, ElMessage, ElNotification} from 'element-plus'

const route = useRoute()
const router = useRouter()
const uStore = UserStore()
const tabsAreaRef = ref(null)
let sortableInstance = null

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
    onEnd({oldIndex, newIndex}) {
      if (oldIndex == null || newIndex == null || oldIndex === newIndex) return
      uStore.reorderTabs(oldIndex, newIndex)
      nextTick(initSortable)
    }
  })
}

onMounted(() => nextTick(initSortable))
watch(() => uStore.tabs.length, () => nextTick(initSortable))
onBeforeUnmount(() => sortableInstance?.destroy())

function clickTab(ele) {
  router.push(ele.props.name)
}

function clickDelete(item) {
  uStore.deleteTabs(item)
}

function clearAllTabs() {
  ElMessageBox.confirm(
      '确定要关闭所有标签吗？',
      '提示', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning',
        center: true
      })
      .then(async () => {
        ElNotification({
          title: '已为您关闭所有标签！',
          type: 'success',
          duration: 1500
        })
        uStore.clearAllTabs()
      })
      .catch(() => {
        ElMessage({
          type: 'info',
          message: '已取消关闭操作。',
          duration: 1500
        })
      })
}
</script>

<style scoped lang="scss">
@use "./Tab.scss";
</style>
