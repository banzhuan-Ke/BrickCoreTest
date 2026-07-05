<template>
  <div class="app-context-block">
    <div class="block-title">App 执行上下文</div>
    <el-form label-width="110px" class="context-form">
      <el-form-item label="目标应用">
        <el-input
          v-model="modelValue.app_id"
          placeholder="Android 包名，如 com.example.app（建议填写，首步 launch_app 使用）"
          clearable
        />
      </el-form-item>
      <el-form-item label="驱动模式">
        <el-select v-model="modelValue.driver_mode" style="width: 100%;">
          <el-option label="混合（原生+图像）" value="hybrid" />
          <el-option label="原生控件" value="native" />
          <el-option label="图像识别" value="vision" />
          <el-option label="混合 WebView" value="hybrid_web" />
          <el-option label="手机 Chrome H5" value="mobile_chrome" />
        </el-select>
      </el-form-item>
      <el-form-item label="登录策略">
        <el-radio-group v-model="modelValue.login_strategy">
          <el-radio value="none">仅功能用例描述</el-radio>
          <el-radio value="credentials">附加测试账号</el-radio>
          <el-radio value="prepend_login">引用登录 App 用例</el-radio>
          <el-radio value="both">账号 + 引用登录</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item v-if="needsCredentials" label="测试账号">
        <div class="account-row">
          <el-input v-model="modelValue.test_username" placeholder="用户名" style="width: 160px;" />
          <el-input
            v-model="modelValue.test_password"
            placeholder="密码"
            type="password"
            show-password
            style="width: 160px;"
          />
        </div>
      </el-form-item>
      <el-form-item v-if="needsLoginCase" label="登录 App 用例">
        <el-select
          v-model="modelValue.login_app_case_id"
          clearable
          filterable
          placeholder="选择已维护的登录 App 用例"
          style="width: 100%;"
        >
          <el-option
            v-for="c in appCaseOptions"
            :key="c.id"
            :label="`${c.name} (#${c.id})`"
            :value="c.id"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="细节补充">
        <el-input
          v-model="modelValue.extra_context"
          type="textarea"
          :rows="3"
          placeholder="例如：登录后进入「我的」→「设置」；或补充业务背景（功能用例未写明的部分）"
          maxlength="800"
          show-word-limit
        />
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { appCaseApi } from '@/api'

const props = defineProps({
  modelValue: { type: Object, required: true },
  projectId: { type: [Number, String], required: true },
})

const appCaseOptions = ref([])

const needsCredentials = computed(() =>
  ['credentials', 'both'].includes(props.modelValue.login_strategy)
)
const needsLoginCase = computed(() =>
  ['prepend_login', 'both'].includes(props.modelValue.login_strategy)
)

const ensureDefaults = () => {
  const m = props.modelValue
  if (m.app_id === undefined) m.app_id = ''
  if (m.driver_mode === undefined) m.driver_mode = 'hybrid'
  if (m.test_username === undefined) m.test_username = ''
  if (m.test_password === undefined) m.test_password = ''
  if (m.login_app_case_id === undefined) m.login_app_case_id = null
  if (m.login_strategy === undefined) m.login_strategy = 'none'
  if (m.extra_context === undefined) m.extra_context = ''
}

const loadAppCases = async () => {
  if (!props.projectId) return
  try {
    const res = await appCaseApi.list({ project_id: props.projectId, page: 1, size: 500 })
    appCaseOptions.value = res.data?.data || res.data || []
  } catch (e) {
    console.error(e)
  }
}

onMounted(() => {
  ensureDefaults()
  loadAppCases()
})
</script>

<style scoped lang="scss">
.app-context-block {
  margin-bottom: 12px;
  padding: 12px 12px 4px;
  background: var(--el-fill-color-light);
  border-radius: 8px;
}
.block-title {
  font-weight: 600;
  margin-bottom: 10px;
  font-size: 14px;
}
.account-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
</style>
