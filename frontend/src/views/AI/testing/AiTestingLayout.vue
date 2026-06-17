<template>
  <PageCard>
    <template #title>
      <div class="hub-title">
        <span>🧪 需求测试中心</span>
      </div>
    </template>
    <template #main>
      <router-view />
    </template>
  </PageCard>
</template>

<script setup>
import PageCard from '@/components/PageCard.vue'
</script>

<style scoped>
.hub-title {
  font-size: 18px;
  font-weight: bold;
}
</style>
