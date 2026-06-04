import { UserStore } from '@/stores/module/UserStore'

export const vPermission = {
  mounted(el, binding) {
    const uStore = UserStore()
    const perm = binding.value
    if (!perm) return
    if (!uStore.hasPermission(perm)) {
      el.remove()
    }
  }
}
