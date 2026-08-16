<template>
  <PageCard>
    <template #title>
      <el-button type="primary" size="small" @click="ClickAdd" icon="Plus">任务</el-button>
    </template>
    <template #main>
      <div style="margin-bottom: 15px; display: flex; gap: 10px; flex-wrap: wrap;">
        <el-input
          v-model="searchForm.name"
          placeholder="搜索任务名称"
          clearable
          style="width: 180px;"
          @keyup.enter="handleSearch"
        />
        <el-select v-model="searchForm.run_type" placeholder="任务类型" clearable style="width: 130px;">
          <el-option label="时间间隔" value="Interval"/>
          <el-option label="固定时间" value="date"/>
          <el-option label="表达式" value="crontab"/>
        </el-select>
        <el-select v-model="searchForm.state" placeholder="状态" clearable style="width: 110px;">
          <el-option label="启用" :value="true"/>
          <el-option label="停用" :value="false"/>
        </el-select>
        <el-button type="primary" @click="handleSearch" icon="Search">搜索</el-button>
        <el-button @click="resetSearch" icon="RefreshRight">重置</el-button>
      </div>
      <el-table :data="cronjobList" style="width: 100%" :header-cell-style="{'text-align':'center'}"
                :cell-style="{'text-align':'center'}" stripe>
        <template #empty>
          <div class="table-empty">
            <div class="empty-icon">
              <el-icon :size="40" color="#909399"><Clock /></el-icon>
            </div>
            <div>暂无数据</div>
          </div>
        </template>
        <el-table-column label="序号" type="index" width="90"/>
        <el-table-column prop="name" label="任务名称"/>
        <el-table-column prop="run_type" label="任务类型">
          <template #default="scope">
            <el-tag v-if='scope.row.run_type==="Interval"' type="primary">时间间隔</el-tag>
            <el-tag v-else-if='scope.row.run_type==="date"' type="info">固定时间</el-tag>
            <el-tag v-else-if='scope.row.run_type==="crontab"' type="success">表达式</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="run_type" label="执行策略" width="300" show-overflow-tooltip>
          <template #default="scope">
            <div v-if='scope.row.run_type==="Interval"' type="primary">
              每{{ scope.row.interval }}秒执行一次
            </div>
            <div v-if='scope.row.run_type==="date"' type="primary">
              固定执行时间：{{ dateTools.rTime(scope.row.date) }}
            </div>
            <div v-if='scope.row.run_type==="crontab"' type="primary">
              表达式：
              <span>{{ scope.row.crontab.minute + ' ' }}</span>
              <span>{{ scope.row.crontab.hour + ' ' }}</span>
              <span>{{ scope.row.crontab.day + ' ' }}</span>
              <span>{{ scope.row.crontab.month + ' ' }}</span>
              <span>{{ scope.row.crontab.day_of_week + ' ' }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="env_name" label="测试环境"/>
        <el-table-column prop="task_name" label="测试计划"/>
        <el-table-column prop="username" label="创建人"/>
        <el-table-column prop="create_time" label="创建时间" width="180">
          <template #default="scope">
            {{ dateTools.rTime(scope.row.create_time) }}
          </template>
        </el-table-column>
        <el-table-column label="更新时间" min-width="180">
          <template #default="scope">
            {{ dateTools.rTime(scope.row.update_time) }}
          </template>
        </el-table-column>
        <el-table-column prop="state" label="状态">
          <template #default="scope">
            <el-switch v-model="scope.row.state" @change="updateCronjobStatus(scope.row.id)"/>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="280">
          <template #default="scope">
            <el-button-group>
              <el-button type="success" size="small" @click="showRecords(scope.row)" icon="List" title="执行记录">
                记录
              </el-button>
              <el-button type="primary" size="small" icon="Edit" @click="EditDialog(scope.row)" title="编辑">
                编辑
              </el-button>
              <el-button type="danger" size="small" @click="deleteCronjob(scope.row.id)" icon="Delete" title="删除">
                删除
              </el-button>
            </el-button-group>
          </template>
        </el-table-column>
      </el-table>
    </template>
  </PageCard>
  
  <!-- 执行记录弹窗 -->
  <el-dialog v-model="recordDialogVisible" :title="`定时任务执行记录 - ${selectedCronjob?.name || ''}`" width="85%" center destroy-on-close>
    <el-table :data="recordList" style="width: 100%" :header-cell-style="{'text-align':'center'}"
              :cell-style="{'text-align':'center'}" stripe v-loading="recordLoading">
      <template #empty>
        <div class="table-empty">
          <div class="empty-icon">
            <el-icon :size="40" color="#909399"><Clock /></el-icon>
          </div>
          <div>暂无执行记录</div>
        </div>
      </template>
      <el-table-column label="序号" type="index" :index="recordTableRowIndex" width="80"/>
      <el-table-column prop="task_name" label="任务名称" show-overflow-tooltip min-width="150"/>
      <el-table-column label="浏览器" prop="env.browser_type" width="100">
        <template #default="scope">
          <el-tag v-if="scope.row.env?.browser_type === 'chromium'" type="success" size="small">谷歌</el-tag>
          <el-tag v-else-if="scope.row.env?.browser_type === 'firefox'" type="warning" size="small">火狐</el-tag>
          <el-tag v-else-if="scope.row.env?.browser_type === 'webkit'" type="info" size="small">Safari</el-tag>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column label="Base_url" show-overflow-tooltip min-width="180">
        <template #default="scope">
          {{ scope.row.env?.host || '-' }}
        </template>
      </el-table-column>
      <el-table-column prop="status" label="执行状态" width="100">
        <template #default="scope">
          <el-tag v-if="scope.row.status === '执行完成'" type="success" size="small">执行成功</el-tag>
          <el-tag v-else-if="scope.row.status === '执行中'" type="primary" size="small">执行中</el-tag>
          <el-tag v-else-if="scope.row.status === '等待执行'" type="info" size="small">等待执行</el-tag>
          <span v-else>{{ scope.row.status }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="case_count" label="用例总数" width="90"/>
      <el-table-column prop="success" label="成功" width="70">
        <template #default="scope">
          <span style="color: var(--el-color-success); font-weight: bold;">{{ scope.row.success }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="fail" label="失败" width="70">
        <template #default="scope">
          <span style="color: var(--el-color-danger); font-weight: bold;">{{ scope.row.fail }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="error" label="错误" width="70">
        <template #default="scope">
          <span style="color: var(--el-color-warning); font-weight: bold;">{{ scope.row.error }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="skip" label="跳过" width="70">
        <template #default="scope">
          <span style="color: var(--el-color-info);">{{ scope.row.skip }}</span>
        </template>
      </el-table-column>
      <el-table-column label="通过率" width="100">
        <template #default="scope">
          <el-progress 
            :percentage="scope.row.pass_rate || 0"
            :status="scope.row.pass_rate === 100 ? 'success' : ''"
            :stroke-width="8"
          />
        </template>
      </el-table-column>
      <el-table-column prop="username" label="执行人" width="100"/>
      <el-table-column prop="start_time" label="执行时间" min-width="160">
        <template #default="scope">
          {{ dateTools.rTime(scope.row.start_time) }}
        </template>
      </el-table-column>
      <el-table-column prop="duration" label="耗时" width="90">
        <template #default="scope">
          {{ scope.row.duration?.toFixed(2) || '0.00' }}秒
        </template>
      </el-table-column>
      <el-table-column label="操作" width="120" fixed="right">
        <template #default="scope">
          <el-button type="primary" size="small" @click="viewReport(scope.row)" icon="View">
            报告
          </el-button>
        </template>
      </el-table-column>
    </el-table>
    <template #footer>
      <div style="display: flex; justify-content: space-between; align-items: center;">
        <el-pagination
          v-model:current-page="recordPage.page"
          v-model:page-size="recordPage.size"
          :page-sizes="[10, 20, 30, 50]"
          layout="total, sizes, prev, pager, next, jumper"
          :total="recordPage.total"
          @current-change="getCronjobRecords"
          @size-change="getCronjobRecords"
        />
        <el-button @click="recordDialogVisible = false">关闭</el-button>
      </div>
    </template>
  </el-dialog>


  
  <!--新建定时任务-->
  <el-dialog v-model="createDialog" title="添加定时任务" width="920" center destroy-on-close>
    <el-form :model="cronjob" :rules="formDataRules" ref="formDataRef" label-width="auto" style="max-width: 750px">
      <el-form-item label="任务名称：" prop="name">
        <el-input v-model="cronjob.name" placeholder="请输入任务名称"/>
      </el-form-item>
      <el-form-item label="测试环境：" prop="env">
        <el-select v-model="cronjob.env" placeholder="请选择测试环境">
          <el-option v-for="item in proStore.envList" :key="item.id" :label="item.name" :value="item.id"/>
        </el-select>
      </el-form-item>
      <el-form-item label="测试计划：" prop="task">
        <el-select v-model="cronjob.task" placeholder="请选择测试计划">
          <el-option v-for="item in proStore.taskList" :key="item.id" :label="item.name" :value="item.id"/>
        </el-select>
      </el-form-item>
      <el-form-item label="创建人：" prop="username">
        <el-input v-model="cronjob.username" disabled></el-input>
      </el-form-item>
      <el-form-item label="执行类型：" prop="run_type">
        <el-radio-group v-model="cronjob.run_type">
          <el-radio-button label="Interval">间隔执行</el-radio-button>
          <el-radio-button label="date">固定时间</el-radio-button>
          <el-radio-button label="crontab">Cron表达式</el-radio-button>
        </el-radio-group>
      </el-form-item>
      
      <!-- 间隔执行 -->
      <template v-if="cronjob.run_type === 'Interval'">
        <el-form-item label="间隔时间：" prop="interval">
          <el-input-number v-model="cronjob.interval" :min="1" :step="60" style="width: 150px"/>
          <span style="margin-left: 10px; color: #666;">秒</span>
          <span v-if="cronjob.interval >= 60" style="margin-left: 10px; color: #909399;">
            ({{ Math.floor(cronjob.interval / 60) }}分钟)
          </span>
        </el-form-item>
      </template>
      
      <!-- 固定时间 -->
      <template v-if="cronjob.run_type === 'date'">
        <el-form-item label="执行时间：" prop="date">
          <el-date-picker
            v-model="cronjob.date"
            type="datetime"
            placeholder="选择执行时间"
            value-format="YYYY-MM-DD HH:mm:ss"
          />
        </el-form-item>
      </template>
      
      <!-- Cron表达式 -->
      <template v-if="cronjob.run_type === 'crontab'">
        <el-form-item label="分：" prop="crontab.minute">
          <el-input v-model="cronjob.crontab.minute" placeholder="*" style="width: 120px" />
        </el-form-item>
        <el-form-item label="时：" prop="crontab.hour">
          <el-input v-model="cronjob.crontab.hour" placeholder="*" style="width: 120px" />
        </el-form-item>
        <el-form-item label="日：" prop="crontab.day">
          <el-input v-model="cronjob.crontab.day" placeholder="*" style="width: 120px" />
        </el-form-item>
        <el-form-item label="月：" prop="crontab.month">
          <el-input v-model="cronjob.crontab.month" placeholder="*" style="width: 120px" />
        </el-form-item>
        <el-form-item label="周：" prop="crontab.day_of_week">
          <el-input v-model="cronjob.crontab.day_of_week" placeholder="*" style="width: 120px" />
        </el-form-item>
        
        <el-form-item>
          <el-alert
            title="Cron 表达式说明"
            type="info"
            :closable="false"
          >
            <template #default>
              <div style="font-size: 13px; line-height: 1.8;">
                <div><strong>* * * * *</strong> 分别表示：分、时、日、月、周</div>
                <div style="margin-top: 8px;">
                  <div><strong>分(minute)：</strong>从0到59之间的任何整数</div>
                  <div><strong>时(hour)：</strong>从0到23之间的任何整数</div>
                  <div><strong>日(day)：</strong>从1到31之间的任何整数</div>
                  <div><strong>月(month)：</strong>从1到12之间的任何整数</div>
                  <div><strong>周(day_of_week)：</strong>从0到7之间的任何整数（0或7代表星期日）</div>
                </div>
                <div style="margin-top: 10px;"><strong>配置案例：</strong></div>
                <div style="margin-top: 5px;">
                  <div><code>5 * * * *</code> 每小时的第5分钟执行一次</div>
                  <div><code>30 9 * * *</code> 每天上午9:30执行一次</div>
                  <div><code>30 9 8 * *</code> 每月8号上午9:30执行一次</div>
                  <div><code>30 9 5 3 *</code> 每年3月5日9:30执行一次</div>
                  <div><code>30 9 * * 7</code> 每星期日上午9:30执行一次</div>
                  <div><code>*/5 * * * *</code> 每5分钟执行一次</div>
                </div>
              </div>
            </template>
          </el-alert>
        </el-form-item>
      </template>
      <el-form-item label="状态：" prop="state">
        <el-switch v-model="cronjob.state"/>
      </el-form-item>
      <CronRunConfigFields ref="createRunConfigRef" :task-parallel="createTaskParallel" />
      <div style="text-align: center">
        <el-button type="primary" @click="createCronjob(formDataRef)" plain>保存</el-button>
        <el-button @click="createDialog=false" plain>取消</el-button>
      </div>
    </el-form>
  </el-dialog>
  <!--修改定时任务-->
  <el-dialog v-model="updateDialog" title="编辑定时任务" width="920" center destroy-on-close>
    <el-form :model="update" :rules="formUpdateRules" ref="formUpdateRef" label-width="auto" style="max-width: 750px">
      <el-form-item label="任务名称：" prop="name">
        <el-input v-model="update.name" placeholder="请输入任务名称"/>
      </el-form-item>
      <el-form-item label="测试环境：" prop="env">
        <el-select v-model="update.env" placeholder="请选择测试环境">
          <el-option v-for="item in proStore.envList" :key="item.id" :label="item.name" :value="item.id"/>
        </el-select>
      </el-form-item>
      <el-form-item label="测试计划：" prop="task">
        <el-select v-model="update.task" placeholder="请选择测试计划">
          <el-option v-for="item in proStore.taskList" :key="item.id" :label="item.name" :value="item.id"/>
        </el-select>
      </el-form-item>
      <el-form-item label="创建人：" prop="username">
        <el-input v-model="update.username" disabled></el-input>
      </el-form-item>
      <el-form-item label="任务类型：" prop="run_type">
        <el-select v-model="update.run_type" placeholder="请选择任务类型">
          <el-option label="时间间隔" value="Interval"/>
          <el-option label="固定时间" value="date"/>
          <el-option label="表达式" value="crontab"/>
        </el-select>
      </el-form-item>
      <el-form-item label="任务时间：" prop="date" v-if="update.run_type === 'date'">
        <el-date-picker v-model="update.date" type="datetime" placeholder="请选择日期时间"/>
      </el-form-item>
      <el-form-item label="任务间隔：" prop="interval" v-if="update.run_type === 'Interval'">
        <el-input-number :min="60" :step="60" v-model.number="update.interval" placeholder="请输入任务间隔（60秒）">
          <template #suffix>
            <span>秒</span>
          </template>
        </el-input-number>
      </el-form-item>
      <el-form-item label="表达式：" prop="crontab" v-if="update.run_type === 'crontab'">
        <el-row>
          <el-col :span="4">
            <el-input v-model="update.crontab.minute">
              <template #append>分</template>
            </el-input>
          </el-col>
          <el-col :span="4" style="margin-left: 3px">
            <el-input v-model="update.crontab.hour">
              <template #append>时</template>
            </el-input>
          </el-col>
          <el-col :span="4" style="margin-left: 3px">
            <el-input v-model="update.crontab.day">
              <template #append>日</template>
            </el-input>
          </el-col>
          <el-col :span="4" style="margin-left: 3px">
            <el-input v-model="update.crontab.month">
              <template #append>月</template>
            </el-input>
          </el-col>
          <el-col :span="4" style="margin-left: 3px">
            <el-input v-model="update.crontab.day_of_week">
              <template #append>周</template>
            </el-input>
          </el-col>
        </el-row>
        <el-row>
          <el-col :span="24">
            <h4>规则说明：crontab格式，具体参考官网：https://crontab.guru</h4>
            <div style="font-size: 14px">* * * * * <span
                style="color:#909399">分别表示：minute、hour、day、month、week。</span></div>
            <div style="font-size: 14px">minute：<span style="color:#909399">表示分钟，可以是从0到59之间的任何整数。</span>
            </div>
            <div style="font-size: 14px">hour：<span style="color:#909399">表示小时，可以是从0到23之间的任何整数。</span>
            </div>
            <div style="font-size: 14px">day：<span style="color:#909399">表示日期，可以是从1到31之间的任何整数。</span>
            </div>
            <div style="font-size: 14px">month：<span style="color:#909399">表示月份，可以是从1到12之间的任何整数。</span>
            </div>
            <div style="font-size: 14px">week：<span
                style="color:#909399">表示星期几，可以是从0到7之间的任何整数，这里的0或7代表星期日。</span></div>
          </el-col>
          <el-col :span="24">
            <h4>配置案例：</h4>
            <div style="font-size: 14px">5 * * * * : <span style="color:#909399">每小时的第5分钟执行一次任务。</span>
            </div>
            <div style="font-size: 14px">30 9 * * * : <span style="color:#909399">每天上午的9:30执行一次任务。</span>
            </div>
            <div style="font-size: 14px">30 9 8 * * : <span style="color:#909399">每月8号上午的9:30执行一次任务。</span>
            </div>
            <div style="font-size: 14px">30 9 5 3 * : <span style="color:#909399">每年的3月5日9:30执行一次任务。</span>
            </div>
            <div style="font-size: 14px">30 9 * * 7 : <span style="color:#909399">每星期日的上午9:30执行一次任务。</span>
            </div>
          </el-col>
        </el-row>
      </el-form-item>
      <el-form-item label="状态：" prop="state">
        <el-switch v-model="update.state"/>
      </el-form-item>
      <CronRunConfigFields ref="updateRunConfigRef" :task-parallel="updateTaskParallel" />
      <div style="text-align: center">
        <el-button type="primary" @click="updateCronjob(formUpdateRef)" plain>保存</el-button>
        <el-button @click="updateDialog=false" plain>取消</el-button>
      </div>
    </el-form>
  </el-dialog>
</template>

<script setup>
import {reactive, onMounted, ref, watch, nextTick} from 'vue'
import {Clock, Search, RefreshRight} from "@element-plus/icons-vue"
import http from '@/api/index'
import {ElNotification, ElMessageBox, ElMessage} from "element-plus"
import dateTools from "@/tools/dateTools.js"
import { makeTableRowIndex } from '@/utils/tableIndex'
import {ProjectStore} from "@/stores/module/ProjectStore.js"
import PageCard from "@/components/PageCard.vue"
import CronRunConfigFields from "@/components/CronRunConfigFields.vue"
import {UserStore} from "@/stores/module/UserStore.js"
import {useRouter} from 'vue-router'

const router = useRouter()
const uStore = UserStore()
const proStore = ProjectStore()

let cronjob = reactive({
  name: "定时任务",
  username: uStore.userInfo.username,
  run_type: "",
  state: false,
  project: proStore.projectInfo.id,
  env: 1,
  task: 1,
  interval: 3600,
  crontab: {
    "month": "*",
    "day_of_week": "*",
    "hour": "*",
    "minute": "*",
    "day": "*"
  },
  date: ""
})

let update = reactive({
  id: 0,
  name: "",
  run_type: "",
  state: "",
  project: proStore.projectInfo.id,
  env: "",
  task: "",
  username: "",
  interval: 3600,
  crontab: {
    "month": "*",
    "day_of_week": "*",
    "hour": "*",
    "minute": "*",
    "day": "*"
  },
  date: "2030-01-01 00:00:00"
})
let cronjobList = ref([])

const searchForm = reactive({
  name: '',
  run_type: '',
  state: ''
})

// 执行记录相关
const recordDialogVisible = ref(false)
const recordLoading = ref(false)
const recordList = ref([])
const selectedCronjob = ref(null)
const recordPage = reactive({
  page: 1,
  size: 10,
  total: 0
})

const recordTableRowIndex = makeTableRowIndex(recordPage)



// 挂载数据
onMounted(() => {
  getCronjobList()
  // 确保测试计划下拉框数据已加载
  if (!proStore.taskList || proStore.taskList.length === 0) {
    proStore.getTaskList()
  }
})

async function getCronjobList() {
  const params = {
    project_id: proStore.projectInfo.id
  }
  if (searchForm.name) params.name = searchForm.name
  if (searchForm.run_type) params.run_type = searchForm.run_type
  if (searchForm.state !== '' && searchForm.state !== undefined && searchForm.state !== null) {
    params.state = searchForm.state
  }
  const response = await http.scheduleApi.getList(params)
  if (response.status === 200) {
    cronjobList.value = response.data
  }
}

const handleSearch = () => {
  getCronjobList()
}

const resetSearch = () => {
  searchForm.name = ''
  searchForm.run_type = ''
  searchForm.state = ''
  getCronjobList()
}

// 显示执行记录
async function showRecords(row) {
  selectedCronjob.value = row
  recordDialogVisible.value = true
  recordPage.page = 1
  await getCronjobRecords()
}

// 获取执行记录
async function getCronjobRecords() {
  if (!selectedCronjob.value) return
  
  recordLoading.value = true
  try {
    const response = await http.scheduleApi.getRecords(selectedCronjob.value.id, {
      page: recordPage.page,
      size: recordPage.size
    })
    if (response.status === 200) {
      recordList.value = response.data.data
      recordPage.total = response.data.total
    }
  } catch (error) {
    ElNotification({
      type: 'error',
      title: '获取执行记录失败',
      message: error.response?.data?.detail || '请稍后重试',
      duration: 3000
    })
  } finally {
    recordLoading.value = false
  }
}

// 查看报告（直接跳转到图表模式）
function viewReport(row) {
  recordDialogVisible.value = false
  router.push({
    name: 'taskReport',
    params: {id: row.id},
    query: {mode: 'chart'}
  })
}

const formDataRules = reactive({
  name: [
    {required: true, message: '请输入任务名称', trigger: 'blur'},
    {max: 50, message: '任务名称不得超过50个字符', trigger: 'blur'},
  ],
  env: [
    {required: true, message: '请选择测试环境', trigger: 'blur'},
  ],
  task: [
    {required: true, message: '请选择测试计划', trigger: 'blur'},
  ],
  run_type: [
    {required: true, message: '请选择任务类型', trigger: 'blur'},
  ],
  date: [
    {required: true, message: '请选择任务时间', trigger: 'blur'},
  ],
  interval: [
    {required: true, message: '请输入任务间隔（秒）', trigger: 'blur'},
    {type: 'number', message: '任务间隔必须是数字', trigger: 'blur'},
  ],
  crontab: [
    {required: true, message: '请输入Crontab表达式', trigger: 'blur'},
  ],
})

let createDialog = ref(false)
let updateDialog = ref(false)
const formDataRef = ref()
const createRunConfigRef = ref()
const updateRunConfigRef = ref()
const createTaskParallel = ref(false)
const updateTaskParallel = ref(false)

async function refreshTaskParallel(taskId, targetRef) {
  if (!taskId) {
    targetRef.value = false
    return
  }
  try {
    const detail = await http.taskApi.getDetail(taskId)
    targetRef.value = !!detail.data?.parallel
  } catch {
    const row = (proStore.taskList || []).find((t) => t.id === taskId)
    targetRef.value = !!row?.parallel
  }
}

watch(() => cronjob.task, (id) => {
  if (createDialog.value) refreshTaskParallel(id, createTaskParallel)
})
watch(() => update.task, (id) => {
  if (updateDialog.value) refreshTaskParallel(id, updateTaskParallel)
})

// 点击添加按钮
async function ClickAdd() {
  // 重新加载下拉框数据（避免 localStorage 中存的是旧项目数据）
  await proStore.getEnvironmentList()
  await proStore.getTaskList()
  // 重置表单数据
  Object.assign(cronjob, {
    name: "定时任务",
    username: uStore.userInfo.username,
    run_type: "",
    state: false,
    project: proStore.projectInfo.id,
    env: proStore.envList[0]?.id || 1,
    task: proStore.taskList[0]?.id || 1,
    interval: 3600,
    crontab: {
      "month": "*",
      "day_of_week": "*",
      "hour": "*",
      "minute": "*",
      "day": "*"
    },
    date: "2030-01-01 00:00:00"
  })
  createDialog.value = true
  await nextTick()
  await refreshTaskParallel(cronjob.task, createTaskParallel)
  await createRunConfigRef.value?.reset(null)
}

async function createCronjob() {
  const valid = await formDataRef.value.validate().catch(() => false)
  if (!valid) return
  const params = {
    ...cronjob,
    date: dateTools.rTime(cronjob.date),
    run_config: createRunConfigRef.value?.buildPayload() || null,
  }
  const response = await http.scheduleApi.create(params)
  if (response.status === 201) {
    createDialog.value = false
    ElNotification({
      type: 'success',
      title: '已成功新建定时任务！',
      duration: 1500,
    })
    await getCronjobList()
  } else {
    ElNotification({
      title: '新建定时任务失败！',
      message: response.data.detail,
      type: 'error',
      duration: 1500
    })
  }
}

async function EditDialog(row) {
  // 重新加载下拉框数据（避免 localStorage 中存的是旧项目数据）
  await proStore.getEnvironmentList()
  await proStore.getTaskList()
  updateDialog.value = true
  update.id = row.id
  update.name = row.name
  update.env = row.env
  update.task = row.task
  update.username = row.username
  update.run_type = row.run_type
  update.state = row.state
  update.date = dateTools.rTime(row.date)
  update.interval = row.interval
  update.crontab = row.crontab
  await nextTick()
  await refreshTaskParallel(update.task, updateTaskParallel)
  await updateRunConfigRef.value?.reset(row.run_config || null)
}

const formUpdateRules = reactive({
  name: [
    {required: true, message: '请输入任务名称', trigger: 'blur'},
    {max: 50, message: '任务名称不得超过50个字符', trigger: 'blur'},
  ],
  env: [
    {required: true, message: '请选择测试环境', trigger: 'blur'},
  ],
  task: [
    {required: true, message: '请选择测试计划', trigger: 'blur'},
  ],
  run_type: [
    {required: true, message: '请选择任务类型', trigger: 'blur'},
  ],
  date: [
    {required: true, message: '请选择任务时间', trigger: 'blur'},
  ],
  interval: [
    {required: true, message: '请输入任务间隔（秒）', trigger: 'blur'},
    {type: 'number', message: '任务间隔必须是数字', trigger: 'blur'},
  ],
  crontab: [
    {required: true, message: '请输入Crontab表达式', trigger: 'blur'},
  ]
})

// 表单引用对象
const formUpdateRef = ref()

async function updateCronjob() {
  const valid = await formUpdateRef.value.validate().catch(() => false)
  if (!valid) return
  const params = {
    ...update,
    date: dateTools.rTime(update.date),
    crontab: {
      minute: update.crontab.minute,
      hour: update.crontab.hour,
      day: update.crontab.day,
      month: update.crontab.month,
      day_of_week: update.crontab.day_of_week
    },
    run_config: updateRunConfigRef.value?.buildPayload() || null,
  }
  const response = await http.scheduleApi.update(update.id, params)
  if (response.status === 200) {
    updateDialog.value = false
    ElNotification({
      type: 'success',
      title: '已成功修改定时任务！',
      duration: 1500,
    })
    await getCronjobList()
  } else {
    ElNotification({
      title: '修改定时任务失败！',
      message: response.data.detail,
      type: 'error',
      duration: 1500
    })
  }
}

async function deleteCronjob(id) {
  ElMessageBox.confirm(
      '此操作不可恢复，确认删除该定时任务吗？',
      '提示', {
        confirmButtonText: '确认',
        cancelButtonText: '取消',
        center: true,
        type: 'warning',
      })
      .then(async () => {
        const response = await http.scheduleApi.delete(id)
        if (response.status === 200 || response.status === 204) {
          await getCronjobList()
          ElNotification({
            type: 'success',
            title: '定时任务删除成功！',
            duration: 1500
          })
        } else {
          ElNotification({
            title: '定时任务删除失败！',
            message: response.data.detail,
            type: 'error',
            duration: 1500
          })
        }
      })
      .catch(() => {
        ElMessage({
          type: 'info',
          message: '已取消删除操作。',
          duration: 1500,
        })
      })
}

// 修改任务状态
async function updateCronjobStatus(id) {
  const response = await http.scheduleApi.toggle(id)
  if (response.status === 200) {
    ElNotification({
      type: 'success',
      title: '任务状态更新成功！',
      duration: 1500
    })
    await getCronjobList()
  } else {
    ElNotification({
      title: '任务状态更新失败！',
      message: response.data.detail,
      type: 'error',
      duration: 1500
    })
  }
}
</script>

<style scoped>
/* 报告选择按钮样式 */
.mode-button {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 20px 30px;
  gap: 8px;
}

.mode-button .el-icon {
  font-size: 24px;
}

/* 进度条样式优化 */
:deep(.el-progress) {
  .el-progress-bar__inner {
    border-radius: 4px;
  }
}
</style>
