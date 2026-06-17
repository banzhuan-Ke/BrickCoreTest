import { defineAsyncComponent } from 'vue'
import MonacoEditorSkeleton from './MonacoEditorSkeleton.vue'

/** 异步加载 Monaco，仅在组件实际渲染时拉取 monaco 分包 */
export default defineAsyncComponent({
  loader: () => import('./MonacoEditor.vue'),
  loadingComponent: MonacoEditorSkeleton,
  delay: 80,
})
