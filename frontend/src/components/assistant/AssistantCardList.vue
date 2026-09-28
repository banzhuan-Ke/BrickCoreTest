<template>
  <div v-if="cards.length" class="assistant-card-list">
    <template v-for="(card, i) in cards" :key="cardKey(card, i)">
      <!-- Confirm：由外层 pending_confirm 兼容渲染，此处跳过避免双份 -->
      <AssistantAskUserCard
        v-if="card.type === 'ask_user' && !askDone"
        :card="card"
        :loading="askLoading"
        @submit="$emit('ask-submit', card, $event)"
        @cancel="$emit('ask-cancel', card)"
      />
      <AssistantSkillResultCard
        v-else-if="card.type === 'skill_result'"
        :card="card"
        :skill-labels="skillLabels"
      />
      <AssistantEntityCard v-else-if="card.type === 'entity'" :card="card" />
      <AssistantJobProgressCard
        v-else-if="card.type === 'job_progress'"
        :card="card"
        :cancelling="cancellingLinkId === (card.link_id || card.id)"
        @cancel="$emit('job-cancel', card)"
      />
    </template>
  </div>
</template>

<script setup>
import AssistantAskUserCard from './AssistantAskUserCard.vue'
import AssistantSkillResultCard from './AssistantSkillResultCard.vue'
import AssistantEntityCard from './AssistantEntityCard.vue'
import AssistantJobProgressCard from './AssistantJobProgressCard.vue'

defineProps({
  cards: { type: Array, default: () => [] },
  askDone: { type: Boolean, default: false },
  askLoading: { type: Boolean, default: false },
  skillLabels: { type: Object, default: () => ({}) },
  cancellingLinkId: { type: [Number, String], default: null }
})

defineEmits(['ask-submit', 'ask-cancel', 'job-cancel'])

const cardKey = (card, i) => {
  if (card?.type === 'ask_user') return `ask-${card.ask_id || i}`
  if (card?.type === 'skill_result') return `skill-${card.skill_code}-${card.run_record_id || i}`
  if (card?.type === 'entity') return `ent-${card.entity_type}-${card.entity_id}`
  if (card?.type === 'confirm') return `confirm-${card.confirm_token || i}`
  if (card?.type === 'job_progress') return `job-${card.link_id || card.job_id || i}`
  return `card-${i}`
}
</script>

<style scoped lang="scss">
.assistant-card-list {
  margin-top: 4px;
}
</style>
