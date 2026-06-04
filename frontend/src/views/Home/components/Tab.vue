<template>
  <div class="box">
    <div class="tabs">
      <!-- 关闭所有按钮 -->
      <div class="button-wrapper">
        <el-button type="danger" @click="clearAllTabs" v-if="uStore.tabs.length > 0">全部关闭</el-button>
      </div>
      <div class="tabs-area">
        <el-tabs icon="UserFilled" v-model='route.path' @tab-click="clickTab" @tab-remove='clickDelete'>
          <div v-for='i in uStore.tabs'>
            <el-tab-pane v-if='route.path !==i.path' :name="i.path" closable>
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
import {UserStore} from '@/stores/module/UserStore'
import {useRoute, useRouter} from 'vue-router'
import {ElMessageBox, ElMessage, ElNotification} from 'element-plus'

// 获取当前路由对象
const route = useRoute()
const router = useRouter()
const uStore = UserStore()

// 点击选项卡
function clickTab(ele) {
  router.push(ele.props.name)
}

// 点击删除的方法
function clickDelete(item) {
  uStore.deleteTabs(item)
}

// 关闭所有标签
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