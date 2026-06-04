import { ref, computed } from 'vue'
import { aiConfigApi } from '@/api/modules/ai.js'

/**
 * 加载已启用的 AI 模型配置；可选 scene 预填场景绑定模型
 */
export function useAiConfigSelect(options = {}) {
  const scene = options.scene || null
  const configList = ref([])
  const aiConfigId = ref(null)
  const loadingConfigs = ref(false)

  const enabledConfigs = computed(() =>
    configList.value.filter(c => c.is_enabled !== false)
  )

  const loadConfigs = async () => {
    loadingConfigs.value = true
    try {
      const res = await aiConfigApi.getList({ size: 200 })
      if (res.data?.code === 200) {
        configList.value = res.data.data?.list || []
        const enabled = configList.value.filter(c => c.is_enabled !== false)
        if (!aiConfigId.value) {
          if (scene) {
            try {
              const bindRes = await aiConfigApi.getSceneBindings()
              const binding = bindRes.data?.data?.bindings?.find(b => b.scene === scene)
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
  }
}
