<template>
  <el-dropdown trigger="click" @command="onSelect">
    <div class="theme-trigger" :class="{ compact }">
      <el-icon :size="compact ? 18 : 20">
        <Brush />
      </el-icon>
      <span v-if="!compact" class="theme-label">{{ currentLabel }}</span>
    </div>
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item
          v-for="opt in UI_THEME_OPTIONS"
          :key="opt.value"
          :command="opt.value"
          :class="{ 'is-active-theme': uStore.uiTheme === opt.value }"
        >
          <div class="theme-option">
            <span class="theme-option__title">{{ opt.label }}</span>
            <span class="theme-option__desc">{{ opt.desc }}</span>
          </div>
          <el-icon v-if="uStore.uiTheme === opt.value" class="theme-check">
            <Check />
          </el-icon>
        </el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<script setup>
import {computed} from 'vue'
import {UserStore} from '@/stores/module/UserStore'
import {UI_THEME_OPTIONS} from '@/utils/theme'

defineProps({
  compact: { type: Boolean, default: false },
})

const uStore = UserStore()

const currentLabel = computed(() => {
  const found = UI_THEME_OPTIONS.find((o) => o.value === uStore.uiTheme)
  return found?.label ?? '界面风格'
})

function onSelect(theme) {
  uStore.setUiTheme(theme)
}
</script>

<style scoped lang="scss">
.theme-trigger {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s ease;
  color: var(--el-text-color-regular);

  &:hover {
    background: var(--el-color-primary-light-9);
    color: var(--el-color-primary);
  }

  &.compact {
    padding: 8px;
  }
}

.theme-label {
  font-size: 13px;
  font-weight: 500;
  max-width: 72px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

:deep(.el-dropdown-menu__item) {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-width: 220px;
  padding: 10px 16px;

  &.is-active-theme {
    color: var(--el-color-primary);
    background: var(--el-color-primary-light-9);
  }
}

.theme-option {
  display: flex;
  flex-direction: column;
  gap: 2px;

  &__title {
    font-size: 13px;
    font-weight: 600;
  }

  &__desc {
    font-size: 11px;
    color: var(--el-text-color-secondary);
    line-height: 1.3;
  }
}

.theme-check {
  color: var(--el-color-primary);
  margin-left: 8px;
}
</style>
