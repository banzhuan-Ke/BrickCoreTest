import { ref } from 'vue'
import { loginPageApi } from '@/api/modules/sys.js'
import {
  LOGIN_PAGE_DEFAULTS,
  buildLoginBackgroundStyle,
} from '@/constants/loginPageBackgrounds.js'
import { UserStore } from '@/stores/module/UserStore'

const cachedConfig = ref(null)
let loadingPromise = null

export function useLoginPageConfig() {
  const uStore = UserStore()

  async function loadLoginPageConfig(force = false) {
    if (cachedConfig.value && !force) {
      return cachedConfig.value
    }
    if (loadingPromise && !force) {
      return loadingPromise
    }
    loadingPromise = loginPageApi
      .getPublicConfig()
      .then((res) => {
        const data = res?.data ?? res ?? {}
        cachedConfig.value = { ...LOGIN_PAGE_DEFAULTS, ...data }
        return cachedConfig.value
      })
      .catch(() => {
        cachedConfig.value = { ...LOGIN_PAGE_DEFAULTS }
        return cachedConfig.value
      })
      .finally(() => {
        loadingPromise = null
      })
    return loadingPromise
  }

  function getBackgroundStyle(config) {
    const cfg = config || cachedConfig.value || LOGIN_PAGE_DEFAULTS
    return buildLoginBackgroundStyle(cfg, uStore.uiTheme)
  }

  function invalidateLoginPageConfigCache() {
    cachedConfig.value = null
  }

  return {
    cachedConfig,
    loadLoginPageConfig,
    getBackgroundStyle,
    invalidateLoginPageConfigCache,
  }
}
