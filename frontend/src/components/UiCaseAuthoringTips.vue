<template>
  <el-collapse v-model="active" class="ui-case-authoring-tips">
    <el-collapse-item name="guide">
      <template #title>
        <span class="ui-case-authoring-tips__title">
          <el-icon><Reading /></el-icon>
          Web 用例编写指南（本平台详细版）
          <el-tag size="small" type="info" effect="plain">默认折叠 · 点击展开</el-tag>
        </span>
      </template>

      <div class="ui-case-authoring-tips__body">
        <p class="ui-case-authoring-tips__lead">
          以下说明<strong>完全按本平台左侧关键字与步骤弹窗字段</strong>编写。用法：左侧拖入关键字 → 打开步骤弹窗填参数 → 保存。
          定位器写不准时用<strong>交互调试 · 拾取</strong>（编辑页）。变量：<code v-pre>${{变量名}}</code>。
          慢站超时优先配<strong>环境管理 → Web 慢站执行策略</strong>。
        </p>

        <el-collapse v-model="chapterActive" class="ui-case-authoring-tips__chapters">
          <el-collapse-item
            v-for="chapter in chapters"
            :key="chapter.id"
            :name="chapter.id"
            :title="chapter.title"
          >
            <p v-if="chapter.intro" class="chapter-intro">{{ chapter.intro }}</p>
            <section v-for="block in chapter.blocks" :key="block.title" class="tip-block">
              <h4>{{ block.title }}</h4>
              <p v-if="block.desc">{{ block.desc }}</p>
              <ul v-if="block.points?.length">
                <li v-for="(p, i) in block.points" :key="i">{{ p }}</li>
              </ul>
              <div v-if="block.example" class="tip-example">
                <div class="tip-example__label">本平台步骤示例（按弹窗字段填写）</div>
                <pre>{{ block.example }}</pre>
              </div>
            </section>
          </el-collapse-item>
        </el-collapse>

        <p class="ui-case-authoring-tips__foot">
          文档中心还可查阅「Web 录制与稳定回放」「Web 失败类型与排障」。本面板侧重<strong>手写步骤</strong>时按关键字怎么填。
        </p>
      </div>
    </el-collapse-item>
  </el-collapse>
</template>

<script setup>
import { ref } from 'vue'
import { Reading } from '@element-plus/icons-vue'

const active = ref([])
const chapterActive = ref([])

const chapters = [
  {
    id: 'basics',
    title: '一、入门：加步骤、定位器、变量、运行',
    intro: '新增页与编辑页左侧关键字相同。运行时由「执行设备」上的 BrickCoreRunner 开浏览器，一般不必每条用例都写「打开浏览器」。',
    blocks: [
      {
        title: '推荐流程',
        points: [
          '左侧分组选关键字 → 拖入步骤列表 → 双击打开编辑弹窗',
          '工具栏：AI 生成 / AI 录制 / 插入片段；编辑页另有 AI 优化、智能步骤、交互调试',
          '保存后回用例列表点「运行」，选环境、浏览器、执行设备',
        ],
      },
      {
        title: '定位器（locator）怎么写',
        desc: '弹窗字段名一般是「定位器 / locator」。多个匹配时填「匹配下标 / index」（从 1 开始）。',
        example: `#btnSave
[data-testid="submit"]
input[name="username"]
.get_by_role=button, 提交
get_by_text=查询
get_by_label=用户名
iframe[name="main"]||#ok
//button[contains(.,"保存")]`,
      },
      {
        title: '变量',
        desc: '在步骤弹窗用「插入变量」。环境/项目全局变量、数据工厂、工具函数均可。',
        example: `元素输入 → value：\${{username}}
访问页面 url → url：\${{base_url}}/orders
数据工厂标签：\${{df:订单号}}
工具函数：\${{dt:md5|text=abc}}`,
      },
    ],
  },
  {
    id: 'page-nav',
    title: '二、页面打开、刷新、多标签',
    intro: '左侧分组：「页面操作」。',
    blocks: [
      {
        title: '访问页面 url（open_url）',
        points: [
          '字段 url：必填；可用变量',
          '字段 wait_until：默认 domcontentloaded（慢站推荐）；有长连接/轮询时慎用 load、networkidle',
        ],
        example: `关键字：访问页面 url
url：https://demo.example.com/login
wait_until：domcontentloaded`,
      },
      {
        title: '刷新 / 后退 / 截图',
        example: `刷新页面 → wait_until 可按需
页面后退 → 可选 fallback_url（后退失败时打开该地址）
页面截图 → name：登录页（报告里展示用）`,
      },
      {
        title: '多标签 / 新窗口',
        points: [
          '新建窗口页面：可选 tag，方便后面「切换页面」',
          '切换页面：按 tag / index / title / url 之一',
          '切换到最新页面：点击后弹出新标签时最常用',
          '关闭页面：按同样条件关掉指定标签',
        ],
        example: `1）点击元素 → locator: get_by_text=导出报表
2）切换到最新页面
3）断言页面url地址 → 包含 export 或 download
4）关闭页面（关掉导出页）
5）如需回原页：切换页面 → index: 1 或按 title`,
      },
    ],
  },
  {
    id: 'dialog-js-scroll',
    title: '三、原生弹窗、执行 JS、页面滚动（含具体填法）',
    intro: '仍在「页面操作」。注意：页面里自己画的 Modal/抽屉 ≠ 浏览器原生 alert/confirm。',
    blocks: [
      {
        title: '接受弹窗 / 取消弹窗（原生 alert、confirm、prompt）',
        desc: '这两个关键字是「注册紧随下一步」：先加接受/取消，下一步再点会弹出框的按钮。若下一步没弹出，注册会自动清掉。点击元素高级里也可勾选 accept_dialog / dismiss_dialog（等价快捷方式）。',
        example: `方式 A（独立关键字）：
1）接受弹窗
   prompt_text：（仅 prompt 需要预填输入时填写）
2）点击元素
   locator：get_by_text=删除

方式 B（写在点击上）：
点击元素
locator：get_by_text=删除
accept_dialog：true

自定义页面弹窗（Element Plus 等）：
不要用「接受弹窗」，改用：
点击元素 → get_by_role=button, 确定`,
      },
      {
        title: '执行JavaScript脚本（execute_script）',
        desc: '弹窗字段「JS脚本 / script」：Runner 对当前页执行 page.evaluate(script)。须已打开目标页。跨域 iframe 内 DOM 不能靠主页脚本直接操作，请用 iframe|| 定位的元素关键字。',
        example: `【滚到指定像素】
关键字：执行JavaScript脚本
script：() => { window.scrollTo(0, 800) }

【滚到底】
script：() => { window.scrollTo(0, document.body.scrollHeight) }

【滚内部容器（如表格 body）】
script：() => {
  const el = document.querySelector('.el-table__body-wrapper')
  if (el) el.scrollTop = 500
}

【写入后再读（调试用）】
script：() => {
  localStorage.setItem('flag', '1')
  return localStorage.getItem('flag')
}

【不推荐】用 JS 去点按钮——请改用「点击元素」，便于自愈与报告定位`,
      },
      {
        title: '滚动到指定高度位置（scroll_to_height）',
        desc: '弹窗字段 position + height。平台会优先滚真正可滚动的容器（适合 SPA）；滚不动时会尝试鼠标滚轮兜底。',
        example: `滚到顶部：
关键字：滚动到指定高度位置
position：top

滚到底部：
position：bottom

滚到中间：
position：middle

相对向下滚 800px：
position：down
height：800

相对向上滚：
position：up
height：600

滚到绝对 scrollTop=1200：
position：height
height：1200`,
      },
      {
        title: '滚动到元素（scroll_to_element）',
        desc: '把目标滚进视口后再点/断言。虚拟列表、懒加载常用。',
        example: `关键字：滚动到元素
locator：get_by_text=订单尾部行
index：1
然后：点击元素 / 断言元素可见`,
      },
      {
        title: '鼠标滚动（mouse_wheel）vs 上面两种',
        desc: '在「鼠标键盘」分组。在光标位置派发滚轮，适合必须靠 wheel 事件的组件；一般列表优先用「滚动到元素」或「滚动到指定高度位置」。',
        example: `关键字：鼠标滚动
direction：down
amount：600
cursor_x：640
cursor_y：360
（先把光标移到可滚动区域中心再滚）`,
      },
    ],
  },
  {
    id: 'element',
    title: '四、元素操作：点击、输入、下拉、悬停、拖拽',
    intro: '左侧分组：「元素操作」。点击高级参数可配动作前就绪（ready_selector / use_env_ready）与动作后等待（expected_selector + post_wait_state=reappear 适合查询后列表刷新）。',
    blocks: [
      {
        title: '点击 / 输入 / 清空',
        example: `点击元素
locator：get_by_role=button, 查询
index：1
force：false（仅元素被遮挡且确认要点时再 true）

元素输入
locator：#keyword
value：测试订单
index：1

清空输入框内容
locator：#keyword

键盘输入值（需触发 keydown 的控件）
locator：.el-select__input
value：张三`,
      },
      {
        title: '动作前就绪 / 动作后等列表刷新（高级）',
        example: `点击元素
locator：get_by_text=查询
ready_selector：（可选）本步动作前业务就绪点
use_env_ready：false（默认；true=等环境就绪选择器）
expected_selector：.el-table__row
post_wait_state：reappear
（先等到该选择器消失再出现，避免点完立刻断言旧数据）

wait_busy_after：true
（再短探测环境配置的忙碌遮罩）`,
      },
      {
        title: '点击顺带下载 / 原生弹窗',
        example: `点击元素
locator：get_by_text=导出
wait_download：true
save_path：（可选本机路径）
var_name：downloadPath

点击元素
locator：get_by_text=确定删除
accept_dialog：true`,
      },
      {
        title: '下拉、悬停、复选、拖拽',
        example: `选择下拉框的值
locator：select#status  或  .el-select
value：已完成

鼠标悬停到元素上方
locator：.nav-more
→ 再点击元素：get_by_text=子菜单

选中复选框
locator：input[type=checkbox]

拖拽元素
start_selector：#item-a
end_selector：#item-b
source_index / target_index：1`,
      },
      {
        title: '按文本点击 / 提取',
        example: `按文本点击元素
text：提交审核
（在可见文本中找可点节点）

提取元素文本
locator：.order-no
var_name：orderNo
→ 后续元素输入 value：\${{orderNo}}

提取元素属性
locator：a.download
attr_name：href
var_name：fileUrl

提取当前页面url
var_name：curUrl`,
      },
    ],
  },
  {
    id: 'wait',
    title: '五、等待操作与慢站环境',
    intro: '左侧分组：「等待操作」。少用过长「强制等待时间」；优先等元素 / URL / 接口。',
    blocks: [
      {
        title: '常用等待怎么填',
        example: `等待元素可见
locator：.el-table__row
index：1

等待元素消失
locator：.el-loading-mask

等待元素文本包含 / 变化 / 稳定
locator：.status
（按弹窗字段填期望文本或超时）

等待URL包含
url：/orders

等待接口响应
url：/api/orders
method：GET（可选）
status：200（可选）

等待下载完成
（也可直接在「点击元素」上勾 wait_download）

强制等待时间
seconds：2
（动画偶发不够时的兜底，勿滥用）`,
      },
      {
        title: '慢站（环境配置，不是步骤关键字）',
        points: [
          '环境管理 → Web 慢站执行策略：超时倍率、忙碌选择器、就绪选择器、操作后沉降等',
          '单用例运行弹窗默认超时倍率 1；套件/计划默认跟环境；显式填 1 会强制覆盖环境高倍率',
          '步骤高级配置可填动作前就绪 / 动作后等待；步骤里手填很大 timeout 可能不再乘环境倍率',
        ],
      },
    ],
  },
  {
    id: 'assert',
    title: '六、断言处理',
    intro: '左侧分组：「断言处理」。失败则该步失败。',
    blocks: [
      {
        title: '页面与元素断言示例',
        example: `断言页面标题 → value：订单列表
断言页面url地址 → 包含 /orders

断言元素文本包含
locator：.el-message
value：保存成功

断言元素文本值（完全相等）
locator：.status
value：已完成

断言文本包含 / 不包含（页面可见文本）
value：无权访问

断言元素可见 / 隐藏 / 不存在 / 可用 / 禁用 / 选中
locator：#submitBtn

断言元素数量
locator：.el-table__row
期望数量按弹窗字段填写

断言元素属性值
locator：input#user
attr_name：value
value：admin

数据库断言
（弹窗内配置数据工厂连接与 SQL/断言；需环境已配数据源）`,
      },
    ],
  },
  {
    id: 'iframe',
    title: '七、iframe（含多 iframe）',
    intro: '两种等价方式：① 通用关键字定位器写 iframe||元素；② 左侧「iframe操作」（frame + locator 分栏）。上传见下一章。',
    blocks: [
      {
        title: '通用 || 写法（推荐）',
        example: `点击元素
locator：iframe[name="mainContent"]||#btnSave

元素输入
locator：iframe[src*="order"]||input[name="q"]

两层嵌套：
locator：iframe[name="outer"]||iframe||.btn-ok`,
      },
      {
        title: 'iframe 分组关键字',
        example: `iframe内元素点击
frame：iframe[name="mainContent"]
locator：#btnSave
index：1

iframe内元素输入
frame：iframe#content
locator：#user
value：admin`,
      },
      {
        title: '多 iframe 注意',
        points: [
          '不要只写 iframe（默认第一个，易点错）',
          '用 name / id / src*= 区分',
          '同 iframe 多个相同控件用 index',
        ],
      },
    ],
  },
  {
    id: 'upload',
    title: '八、文件上传（含 iframe 内）',
    intro: '关键字：input文件上传。Runner 对 input[type=file] 执行 set_input_files，不操作系统「打开」对话框。',
    blocks: [
      {
        title: '标准上传',
        points: [
          '先在项目「测试文件」上传素材，步骤弹窗「测试文件」里选择（推荐）',
          '定位器对准真正的 file 输入框（常隐藏），不是「上传」按钮',
          'upload_mode：single / multiple / folder',
        ],
        example: `关键字：input文件上传
locator：input[type=file]
index：1
upload_mode：single
测试文件：证件照.png（平台已上传）

高级：也可填 Runner 本机 file_path，一般优先平台测试文件`,
      },
      {
        title: 'iframe 里上传',
        desc: '仍用 input文件上传；左侧 iframe 分组没有上传项是正常的。定位必须是 input[type=file]，src 属性引号要成对，勿多写一个引号。',
        example: `正确：
locator：iframe[src*="/biz/index"]||input[type=file]

错误（多一个引号，CSS 解析失败）：
locator：iframe[src*="/biz/index""]||input[type=file]
报错类似：Unexpected token "" / Did you mean to CSS.escape it?`,
      },
    ],
  },
  {
    id: 'session',
    title: '九、Cookie / LocalStorage / 鉴权 Token / 导出登录态',
    intro: '在「页面操作」分组。注入前请先「访问页面 url」到目标域名（LocalStorage / 部分 Cookie 需要）。',
    blocks: [
      {
        title: '设置 LocalStorage / SessionStorage',
        example: `1）访问页面 url → \${{base_url}}/
2）设置LocalStorage
   key：token
   value：\${{token}}
3）访问页面 url → \${{base_url}}/home
（或刷新页面让前端读到新 token）`,
      },
      {
        title: '设置Cookie',
        example: `设置Cookie
name：SESSION
value：\${{session}}
domain：.example.com
path：/
（也可只填 url：https://demo.example.com/ ，由当前页推导）`,
      },
      {
        title: '设置鉴权Token',
        desc: '给后续请求加 Header（如 Authorization: Bearer …）；可选同时写入 localStorage。',
        example: `访问页面 url → \${{base_url}}/
设置鉴权Token
token：\${{token}}
header_name：Authorization
header_prefix：Bearer
storage_key：access_token
（storage_key 留空则只设请求头）`,
      },
      {
        title: '导出登录态 / 清空Cookie',
        example: `手工或步骤登录成功并进入业务页后：
导出登录态
path：D:/auth/demo.json
（须带 .json 文件名；新 Runner 会附带 sessionStorageOrigins）
再在环境「Web 启动登录态注入」填同一路径。
会话过期后重新导出，或改用登录步骤片段。

清空Cookie
（重置浏览器上下文 Cookie，需重新登录或再注入）`,
      },
    ],
  },
  {
    id: 'mouse-key',
    title: '十、鼠标键盘（坐标与特殊键）',
    intro: '分组：「鼠标键盘」。能定位到元素时优先用「元素操作」；坐标点击脆弱。',
    blocks: [
      {
        title: '示例',
        example: `键盘按键
key：Enter
（常用 Escape、Tab、ArrowDown 等）

键盘输入文本
keys：hello
（向当前焦点逐字输入）

鼠标点击
x：100
y：200
button：left
count：1

鼠标移动 / 按下 / 抬起：画布拖拽等组合场景`,
      },
    ],
  },
  {
    id: 'vision',
    title: '十一、图像定位',
    intro: '分组：「图像定位」。canvas、无稳定 DOM 时用小图模板。',
    blocks: [
      {
        title: '关键字',
        example: `图像模板点击 → 选择模板图
图像模板输入 → 模板图 + 要输入的文本
等待图像出现 / 断言图像存在 / 断言图像不存在

注意：分辨率、缩放、主题色变化可能导致匹配失败；模板尽量裁小、特征清晰`,
      },
    ],
  },
  {
    id: 'http',
    title: '十二、等待接口与提取响应字段',
    blocks: [
      {
        title: '典型链路',
        example: `1）点击元素 → locator: get_by_text=保存
2）等待接口响应
   url：/api/order/save
   method：POST
   status：200
3）提取接口响应字段
   field：按弹窗说明填 JSON 路径或字段名
   var_name：billId
4）断言或后续输入使用 \${{billId}}`,
      },
    ],
  },
  {
    id: 'ai-cond',
    title: '十三、智能步骤、条件分支、AI 辅助',
    blocks: [
      {
        title: '智能步骤',
        example: `关键字：智能步骤
intent：点击页面上的「提交」按钮并等待成功提示
（执行时再规划；需项目开启相关 AI 能力。≠ 编用例时的「AI 生成步骤」）`,
      },
      {
        title: '条件分支',
        points: [
          '关键字「条件分支」：可按元素可见等走不同子步骤，带默认 else 分支',
          '条件要稳定；复杂流程优先拆用例或片段，避免深嵌套',
        ],
      },
      {
        title: 'AI 生成 / 录制 / 优化',
        points: [
          '工具栏按钮，不是左侧关键字',
          '生成后务必人工过关键路径；录制上传路径会留空，需再绑测试文件',
        ],
      },
    ],
  },
  {
    id: 'elementui-iframe',
    title: '十四、实战排障：ElementUI 多 iframe 弹窗（能点不能输 / 上传失败）',
    intro: '后台壳页多个 iframe（tab 切换、同源嵌入），业务弹窗在 iframe 内（如 ElementUI el-dialog）时的高频问题。',
    blocks: [
      {
        title: '一句话备忘',
        desc: 'ElementUI：点外壳可以，填要落到 input.el-input__inner。新版交互调试拾取会对普通输入下钻，并给出 get_by_role=textbox 等语义候选；仍建议优先选语义项。iframe 上传用「iframe选择器||input[type=file]」，src 引号必须成对。',
      },
      {
        title: '1. 点击可以，输入报错',
        desc: '典型报错：Locator.fill: Element is not an <input>, <textarea>, <select> …；locator resolved to <div class="el-input …">。原因：点到了 ElementUI 外壳 div.el-input——点击可以点外壳，fill 只能打在真正的 input 上。',
        points: [
          '新版拾取默认落到真实 input，并带 textbox / placeholder 候选；若仍是外壳，可选手改或依赖 Runner fill 自动下钻',
          '步骤用「iframe内元素输入」（或通用「元素输入」+ iframe|| 前缀）',
          'iframe 用 iframe[src*="/业务路径"] 或更精确的 iframe[src="/业务路径"] 区分多 iframe',
          '元素定位落到真实 input，不要停在 .el-input 外壳',
          '「强制点击」只对点击有用，输入步骤不必开',
        ],
        example: `关键字：iframe内元素输入
frame：iframe[src*="/biz/order"]
locator：div.el-dialog .el-form-item.is-required input.el-input__inner
value：测试内容

或在原 CSS 末尾补：
… .el-input > input.el-input__inner

通用写法等价：
元素输入
locator：iframe[src*="/biz/order"]||div.el-dialog input.el-input__inner`,
      },
      {
        title: '2. 弹窗按钮必须强制点击',
        desc: '遮罩、动画、未完全可点时，Playwright 常规 click 会失败。步骤打开「强制点击 / force」即可，属常见绕过，不是平台异常。',
        example: `iframe内元素点击（或点击元素 + iframe||）
force：true
locator：div.el-dialog button …（确定/保存等）`,
      },
      {
        title: '3. iframe 内上传文件',
        desc: '用「input文件上传」（不是 iframe 专用步骤）。目标必须是隐藏的 input[type=file]，不要点「点击上传」按钮。文件用平台「测试文件」或本机路径。',
        example: `关键字：input文件上传
locator：iframe[src*="/biz/order"]||input[type=file]
测试文件：选平台文件

引号易错（多一个引号 → CSS 解析失败）：
错误：iframe[src*="/xxx/index""]||input[type=file]
正确：iframe[src*="/xxx/index"]||input[type=file]
报错类似：Unexpected token "" / Did you mean to CSS.escape it?`,
      },
      {
        title: '4. 和「为什么不用 get_by_role」的关系',
        points: [
          '录制/拾取会对「确定」「取消」等常见短词默认降级到 CSS，避免页面多处同文案点错',
          '这与「点到 div.el-input」无关；输入失败优先查是否点到了组件外壳，而不是纠结 role',
        ],
      },
    ],
  },
  {
    id: 'faq',
    title: '十五、常见问题速查',
    blocks: [
      {
        title: '排错对照',
        points: [
          '点了没反应 → 是否在 iframe？locator 加 iframe|| 或用 iframe 分组',
          '能点不能输（ElementUI）→ 定位落到 input.el-input__inner，见第十四章',
          '上传没反应 → 不要操作系统文件框；用 input文件上传 + 测试文件；检查 iframe|| 与引号',
          'JS 滚动无效 → 可能滚错容器；改用滚动到元素，或 JS 里对 .el-table__body-wrapper 设 scrollTop',
          '弹窗没点上 → 原生框用「接受弹窗」紧挨触发点击；ElementUI 遮罩可试强制点击',
          '新窗口断言失败 → 先「切换到最新页面」',
          '时好时坏 → 加等待元素可见，或配环境忙碌/就绪与沉降',
          '匹配错元素 → 收紧 locator 或改 index',
        ],
      },
    ],
  },
]
</script>

<style scoped>
.ui-case-authoring-tips {
  margin-bottom: 16px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  overflow: hidden;
  background: var(--el-fill-color-blank);
}

.ui-case-authoring-tips :deep(.el-collapse-item__header) {
  padding-left: 14px;
  height: 44px;
  line-height: 44px;
  background: var(--el-fill-color-light);
}

.ui-case-authoring-tips :deep(.el-collapse-item__wrap) {
  border-bottom: none;
}

.ui-case-authoring-tips :deep(.el-collapse-item__content) {
  padding: 0 12px 12px;
}

.ui-case-authoring-tips__title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-weight: 500;
  color: var(--el-text-color-primary);
}

.ui-case-authoring-tips__lead,
.ui-case-authoring-tips__foot {
  margin: 10px 4px 0;
  font-size: 13px;
  line-height: 1.55;
  color: var(--el-text-color-regular);
}

.ui-case-authoring-tips__foot {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px dashed var(--el-border-color-lighter);
  color: var(--el-text-color-secondary);
}

.ui-case-authoring-tips__body {
  max-height: min(70vh, 720px);
  overflow: auto;
  padding-right: 4px;
}

.ui-case-authoring-tips__chapters {
  margin-top: 8px;
  border: none;
}

.ui-case-authoring-tips__chapters :deep(.el-collapse-item) {
  margin-top: 6px;
  border: 1px solid var(--el-border-color-extra-light);
  border-radius: 6px;
  overflow: hidden;
}

.ui-case-authoring-tips__chapters :deep(.el-collapse-item__header) {
  height: 40px;
  line-height: 40px;
  background: var(--el-fill-color-blank);
  font-size: 13px;
  font-weight: 500;
}

.ui-case-authoring-tips__chapters :deep(.el-collapse-item__content) {
  padding: 0 12px 12px;
}

.chapter-intro {
  margin: 8px 0 0;
  font-size: 13px;
  line-height: 1.55;
  color: var(--el-text-color-secondary);
}

.tip-block {
  margin-top: 12px;
}

.tip-block h4 {
  margin: 0 0 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.tip-block p {
  margin: 0;
  font-size: 13px;
  line-height: 1.55;
  color: var(--el-text-color-regular);
}

.tip-block ul {
  margin: 6px 0 0;
  padding-left: 1.2em;
  font-size: 13px;
  line-height: 1.55;
  color: var(--el-text-color-regular);
}

.tip-example {
  margin-top: 8px;
  border-radius: 6px;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-extra-light);
  overflow: hidden;
}

.tip-example__label {
  padding: 4px 10px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  border-bottom: 1px solid var(--el-border-color-extra-light);
}

.tip-example pre {
  margin: 0;
  padding: 8px 10px;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-all;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  color: var(--el-text-color-primary);
}

.ui-case-authoring-tips__lead code,
.tip-block code {
  padding: 0 4px;
  border-radius: 3px;
  background: var(--el-fill-color-light);
  font-size: 12px;
}
</style>
