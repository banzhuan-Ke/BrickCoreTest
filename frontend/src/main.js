import {createApp} from 'vue'
import App from './App.vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import router from '@/router/index'
// 导入暗黑模式主题
import 'element-plus/theme-chalk/dark/css-vars.css'
// 导入项目的全局css样式文件
import '@/style/main.css'
import '@/style/theme-pro.css'
import pinia from '@/stores/index'
// 引入nprogress样式
import 'nprogress/nprogress.css'
import {useDark} from '@vueuse/core'
import { vPermission } from '@/directives/permission'

// 创建vue实例
const app = createApp(App)

// 注册权限指令
app.directive('permission', vPermission)

// 注册element-plus
app.use(ElementPlus, {zIndex: 3000, locale: zhCn})
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
    app.component(key, component)
}
// 注册路由
app.use(router)
// 注册pinia
app.use(pinia)

// 添加暗黑模式全局状态
app.provide('dark-mode', useDark())

// 挂载根节点
app.mount('#app')
