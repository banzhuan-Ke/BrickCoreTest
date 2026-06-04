import {createPinia} from 'pinia'
import piniaPluginPersistedstate from 'pinia-plugin-persistedstate'

// 创建一个pinia示例
const pinia = createPinia()

// 将持久化的插件注册到pinia中
pinia.use(piniaPluginPersistedstate)

export default pinia
