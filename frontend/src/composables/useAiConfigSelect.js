import { ref, computed } from 'vue'
import { aiConfigApi } from '@/api/modules/ai.js'

/**
 * 加载已启用的 AI 模型配置；可选 scene 预填场景绑定模型
 */
export function useAiConfigSelect(options = {}) {
  const configList = ref([])
  const aiConfigId = ref(null)
  const loadingConfigs = ref(false)

  const sceneRef = ref(options.scene || null)

  const enabledConfigs = computed(() =>
    configList.value.filter(c => c.is_enabled !== false)
  )

  const setScene = (newScene) => {
    sceneRef.value = newScene || null
  }

  const loadConfigs = async (overrideScene) => {
    loadingConfigs.value = true
    const activeScene = overrideScene ?? sceneRef.value
    try {
      const res = await aiConfigApi.getList({ size: 200 })
      if (res.data?.code === 200) {
        configList.value = res.data.data?.list || []
        const enabled = configList.value.filter(c => c.is_enabled !== false)
        if (!aiConfigId.value || overrideScene !== undefined) {
          if (activeScene) {
            try {
              const bindRes = await aiConfigApi.getSceneBindings()
              const binding = bindRes.data?.data?.bindings?.find(b => b.scene === activeScene)
              if (binding?.config_id && enabled.some(c => c.id === binding.config_id)) {
                aiConfigId.value = binding.config_id
                return
              }
            } catch (e) {
              console.warn('场景绑定预填失败', e)
            }
          }
          const def = enabled.find(c => c.is_default) || enabled[0]
          if (def) aiConfigId.value = def.id
        }
      }
    } catch (e) {
      console.error(e)
    } finally {
      loadingConfigs.value = false
    }
  }

  const resetAiConfigId = () => {
    aiConfigId.value = null
    const def = enabledConfigs.value.find(c => c.is_default) || enabledConfigs.value[0]
    if (def) aiConfigId.value = def.id
  }

  return {
    configList,
    aiConfigId,
    enabledConfigs,
    loadingConfigs,
    loadConfigs,
    resetAiConfigId,
    setScene,
  }
}
