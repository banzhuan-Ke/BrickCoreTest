<template>
  <PageCard v-if="!embedded">
    <template #title>
      <slot name="title" />
    </template>
    <template #main>
      <slot name="main" />
    </template>
    <template v-if="$slots.bottom" #bottom>
      <slot name="bottom" />
    </template>
  </PageCard>
  <div v-else class="config-shell-embedded">
    <slot name="main" />
  </div>
</template>

<script setup>
import PageCard from '@/components/PageCard.vue'

defineProps({
  embedded: { type: Boolean, default: false }
})
</script>

<style scoped>
.config-shell-embedded {
  padding: 4px 0 12px;
  min-height: 120px;
}
</style>
