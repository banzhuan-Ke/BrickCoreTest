<template>
  <ConfigShell :embedded="embedded">
    <template #title>
      <b>小测助手</b>
    </template>
    <template #main>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="多轮助手护栏与上下文压缩"
        description="超时、Token/轮次配额、工具结果压缩与会话摘要阈值均在本页配置，优先生效，不必再改 docker-compose。场景绑定里的模型 timeout 是 HTTP 客户端上限，与本页不是同一层。"
        style="margin-bottom: 20px; max-width: 960px;"
      />

      <el-form :model="form" label-width="240px" style="max-width: 960px;">
        <div class="section-title">超时与配额</div>
        <el-form-item label="单次 LLM 超时（秒）">
          <el-input-number v-model="form.assist_llm_timeout_sec" :min="20" :max="600" :step="10" controls-position="right" />
          <div class="field-hint">每一轮调模型的 wait_for 上限；超时记 stop=llm_timeout。建议 ≥180。</div>
        </el-form-item>
        <el-form-item label="整轮墙钟上限（秒）">
          <el-input-number v-model="form.assist_max_wall_sec" :min="30" :max="600" :step="10" controls-position="right" />
          <div class="field-hint">一次对话总时长；须 ≥ 单次 LLM 超时。建议 ≥240。</div>
        </el-form-item>
        <el-form-item label="整轮累计 Token 上限">
          <el-input-number v-model="form.assist_max_tokens_total" :min="8000" :max="200000" :step="8000" controls-position="right" />
          <div class="field-hint">累计 prompt+补全；超限 stop=token_budget。多工具建议 ≥80000。</div>
        </el-form-item>
        <el-form-item label="最大规划轮次">
          <el-input-number v-model="form.assist_max_plan_rounds" :min="1" :max="12" :step="1" controls-position="right" />
          <div class="field-hint">Agent 最多规划/调工具的轮数；默认 5。</div>
        </el-form-item>
        <el-form-item label="每轮最多工具数">
          <el-input-number v-model="form.assist_max_tools_per_round" :min="1" :max="8" :step="1" controls-position="right" />
          <div class="field-hint">单轮 LLM 可并行调用的工具上限；默认 4。</div>
        </el-form-item>
        <el-form-item label="失败分析最大汇总轮次">
          <el-input-number v-model="form.assist_failure_digest_max_rounds" :min="1" :max="8" :step="1" controls-position="right" />
          <div class="field-hint">失败分析 map-reduce 最大层数；到顶后剩余批次原文保留。</div>
        </el-form-item>

        <div class="section-title">工具结果压缩</div>
        <el-form-item label="工具结果最大字符">
          <el-input-number v-model="form.assist_tool_result_max_chars" :min="2000" :max="20000" :step="1000" controls-position="right" />
          <div class="field-hint">注入 LLM 的单次工具 JSON 上限；默认 6000（更狠压缩，省 Token）。</div>
        </el-form-item>
        <el-form-item label="列表最多保留条数">
          <el-input-number v-model="form.assist_tool_list_item_limit" :min="3" :max="30" :step="1" controls-position="right" />
          <div class="field-hint">list_* 的 items 等列表截断条数；默认 8。</div>
        </el-form-item>

        <div class="section-title">会话摘要</div>
        <el-form-item label="摘要折叠阈值（条）">
          <el-input-number v-model="form.assist_session_summary_trigger" :min="8" :max="40" :step="1" controls-position="right" />
          <div class="field-hint">会话消息超过此数时，更早内容折叠进摘要（不调 LLM）。默认 16。</div>
        </el-form-item>
        <el-form-item label="Loop 注入历史轮数">
          <el-input-number v-model="form.assist_history_turns" :min="2" :max="12" :step="1" controls-position="right" />
          <div class="field-hint">每次 Agent 规划时带入的近期 user/assistant 轮数；默认 4。更早内容靠会话摘要。</div>
        </el-form-item>

        <el-form-item v-if="form.update_time" label="最后修改">
          <span class="meta-text">{{ form.update_by || '—' }} · {{ form.update_time }}</span>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="saving" @click="saveConfig">保存配置</el-button>
        </el-form-item>
      </el-form>
    </template>
  </ConfigShell>
</template>

<script setup>
import { reactive, ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import ConfigShell from '@/components/ConfigShell.vue'
import { platformSettingsApi } from '@/api/modules/sys'

defineProps({
  embedded: { type: Boolean, default: false },
})

const defaults = {
  assist_llm_timeout_sec: 180,
  assist_max_wall_sec: 240,
  assist_max_tokens_total: 80000,
  assist_max_plan_rounds: 5,
  assist_max_tools_per_round: 4,
  assist_failure_digest_max_rounds: 4,
  assist_tool_result_max_chars: 6000,
  assist_tool_list_item_limit: 8,
  assist_session_summary_trigger: 16,
  assist_history_turns: 4,
}

const form = reactive({
  ...defaults,
  update_by: '',
  update_time: '',
})

const saving = ref(false)

const num = (v, fallback) => {
  const n = Number(v)
  return Number.isFinite(n) && n > 0 ? n : fallback
}

const applyData = (data) => {
  Object.keys(defaults).forEach((k) => {
    form[k] = num(data[k], defaults[k])
  })
  form.update_by = data.update_by || ''
  form.update_time = data.update_time || ''
}

const loadConfig = async () => {
  try {
    const res = await platformSettingsApi.getConfig()
    applyData(res?.data ?? res ?? {})
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '加载配置失败')
  }
}

const saveConfig = async () => {
  saving.value = true
  try {
    const payload = {}
    Object.keys(defaults).forEach((k) => {
      payload[k] = form[k]
    })
    const res = await platformSettingsApi.updateConfig(payload)
    applyData(res?.data ?? res ?? {})
    ElMessage.success('小测助手护栏配置已保存（对新对话立即生效）')
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(loadConfig)
</script>

<style scoped>
.section-title {
  margin: 8px 0 16px;
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.meta-text {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.field-hint {
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
  max-width: 560px;
}
</style>
