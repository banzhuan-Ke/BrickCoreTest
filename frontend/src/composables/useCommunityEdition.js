import { ref } from 'vue'
import http from '@/api/request'

const isCommunityEdition = ref(false)
let loadingPromise = null

export function useCommunityEdition() {
  async function loadCommunityEdition(force = false) {
    if (!force && loadingPromise) {
      return loadingPromise
    }
    loadingPromise = http
      .get('/runner/version')
      .then((res) => {
        isCommunityEdition.value = !!res.data?.community_edition
      })
      .catch(() => {
        isCommunityEdition.value = false
      })
    return loadingPromise
  }

  return { isCommunityEdition, loadCommunityEdition }
}
