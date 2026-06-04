<template>
  <div class="help-content">
    <el-scrollbar :height="isHelpFullscreen ? 'calc(100vh - 180px)' : '500px'">
      <div class="help-section">
        <el-alert
          type="info"
          :closable="false"
          show-icon
          title="完整指南建议在「文档中心」维护与查阅；此处为内置快速摘要。"
          style="margin-bottom: 12px;"
        />
        <h3>🚀 快速开始</h3>
        <p>欢迎使用 BrickCore！本平台支持 <strong>Web UI 自动化</strong>、<strong>接口自动化</strong>、<strong>性能测试</strong>和 <strong>AI 自动化测试</strong>四大测试能力，帮助您快速构建完整的自动化测试体系。</p>
        
        <h4>UI 自动化流程：</h4>
        <ol>
          <li><strong>创建项目</strong> → 管理测试项目</li>
          <li><strong>配置环境</strong> → 设置测试网址</li>
          <li><strong>安装执行器</strong> → 设备管理下载 zip，登录后上线（见下方「BrickCore 执行器」）</li>
          <li><strong>编写用例</strong> → 录制测试步骤；编辑页每步可「调试到此步」（无需先保存）</li>
          <li><strong>执行测试</strong> → 选择在线设备，查看测试结果</li>
        </ol>

        <h4>接口自动化流程：</h4>
        <ol>
          <li><strong>创建项目</strong> → 管理测试项目</li>
          <li><strong>配置环境</strong> → 设置基础 URL 与全局变量</li>
          <li><strong>导入接口</strong> → 从 Swagger/Postman 导入或手动创建</li>
          <li><strong>编写用例</strong> → 配置请求、断言、变量提取与脚本</li>
          <li><strong>组建套件</strong> → 按业务场景组合用例并执行</li>
          <li><strong>测试计划</strong> → 编排多个套件/单用例，支持串行/并行</li>
          <li><strong>执行记录</strong> → 查看报告、导出 HTML、邮件推送</li>
          <li><strong>数据工厂</strong> → 配置数据源与 SQL 模板，支持套件前置/后置 SQL 与数据库断言</li>
        </ol>

        <h4>性能测试流程：</h4>
        <ol>
          <li><strong>编写接口用例</strong> → 先创建 API 测试用例</li>
          <li><strong>创建场景</strong> → 选择用例组合，配置压测参数</li>
          <li><strong>执行压测</strong> → 选择环境，一键启动</li>
          <li><strong>查看报告</strong> → QPS、RT 趋势图、接口维度分析</li>
        </ol>

        <h4>AI 需求 / 功能用例流程（推荐）：</h4>
        <ol>
          <li><strong>配置模型</strong> → 「AI 测试 → AI 模型配置」添加文本模型；含图 PRD 另配 Vision 模型（如 qwen-vl）</li>
          <li><strong>上传需求</strong> → 「需求用例生成」上传 PDF/Word，按章节勾选范围</li>
          <li><strong>测试分析</strong> → 生成测试点与测试方案，确认后从测试点展开功能用例</li>
          <li><strong>复制入库</strong> → 需求页勾选用例「导入到用例库」，形成项目级长期资产</li>
          <li><strong>复核导出</strong> → 用例库或需求页编辑、导出禅道 XLSX；库内支持禅道 XLSX 回导</li>
          <li><strong>延伸自动化</strong> → 功能用例库勾选 → AI 生成 / 录制 UI 步骤；或接口模块 AI 生成用例</li>
        </ol>
      </div>

      <el-divider />

      <div class="help-section">
        <h3>🤖 AI 自动化测试（平台特色）</h3>
        <p>
          BrickCore 集成大语言模型（LLM），覆盖<strong>需求文档 → 测试分析 → 禅道功能用例</strong>，以及<strong>接口 / UI 执行用例</strong>的 AI 辅助生成。
          建议优先走「需求 + 测试分析」主线，再按需延伸到接口/UI 自动化。
        </p>

        <h4>前置配置：</h4>
        <ol>
          <li>进入「<strong>AI 测试 → AI 模型配置</strong>」，添加 LLM（支持 DeepSeek / 通义千问 / OpenAI / Claude 等）</li>
          <li>填写 API Key、模型名称、API Base，启用并<strong>设为默认</strong>（未单独选模型时使用）</li>
          <li>需求文档含截图/流程图时，另增一条 <strong>Vision 模型</strong>（如通义 qwen-vl）；纯文本模型无法读图</li>
          <li>可在「Prompt 模板」Tab 微调各场景提示词（API/UI 生成、需求解析、测试点等）</li>
          <li>在「需求用例生成」详情中配置<strong>禅道导入绑定</strong>（产品、模块、研发需求等），生成用例时自动带入</li>
        </ol>

        <h4>菜单结构（AI 测试）：</h4>
        <table class="help-table">
          <thead>
            <tr><th>菜单</th><th>路径</th><th>说明</th></tr>
          </thead>
          <tbody>
            <tr><td>AI 工作台</td><td>/ai-test</td><td>统计、推荐流程、快捷入口、批量任务进度</td></tr>
            <tr><td>测试分析</td><td>/ai-test-analysis</td><td>测试点、方案、导图、从测试点生成功能用例</td></tr>
            <tr><td>需求用例生成</td><td>/ai-requirements</td><td>上传 PRD、章节生成、工作区编辑、导出禅道</td></tr>
            <tr><td>功能用例库</td><td>/ai-functional-cases</td><td>项目级功能用例资产；禅道导入；转 UI 自动化</td></tr>
            <tr><td>AI 模型配置</td><td>/ai-config</td><td>LLM 配置、场景绑定、Prompt 模板</td></tr>
            <tr><td>模型使用情况</td><td>/ai-usage</td><td>Token 统计、场景占比与趋势图表；项目列自动补全</td></tr>
          </tbody>
        </table>

        <h4>五、平台内 AI 助手（小测）</h4>
        <p>路径：任意页面右下角 <strong>小测 · 平台助手</strong>（需 <code>ai_test:view</code>）。</p>
        <ul>
          <li><strong>浮窗</strong>：可拖动、可放大、不遮挡主页面；Markdown 表格与列表正常渲染</li>
          <li><strong>查数</strong>：项目概览、接口/UI/压测、需求、最近失败等自然语言查询</li>
          <li><strong>执行</strong>：跑套件/计划/UI/压测等需 preview → 聊天内点「确认执行」</li>
          <li><strong>多会话</strong>：新建/切换/搜索历史；回答中 suite_id、plan_id 等可点击跳转</li>
          <li>模型场景：<code>platform_assistant</code>，可在「AI 模型配置 → 场景绑定」指定</li>
        </ul>

        <h4>零、AI 工作台（总览入口）</h4>
        <p>路径：<strong>AI 测试 → AI 工作台</strong>。提供项目统计、推荐流程、快捷跳转，以及最近需求 / 最近 AI 生成记录；批量生成进行中时会显示进度条。</p>

        <h4>一、需求文档 → 功能用例</h4>
        <p>路径：<strong>AI 测试 → 需求用例生成</strong>。</p>
        <ol>
          <li><strong>上传文档</strong> → 支持 PDF / Word / TXT / MD，系统自动解析章节树与嵌入图片</li>
          <li><strong>勾选章节</strong> → 选择本次生成范围，可先「预估 Token」避免单次过大</li>
          <li><strong>选择模型</strong> → 文本模型生成用例；有图时选择 Vision 模型读图</li>
          <li><strong>生成用例</strong> → 输出禅道格式（模块、标题、前置、步骤、预期、优先级等），支持单批 / 多批队列异步生成</li>
          <li><strong>补充生成</strong> → 按<strong>批次名称</strong>在已有用例基础上追加，批次名须与首次一致</li>
          <li><strong>编辑导出</strong> → 表格内修改后「导出 XLSX」导入禅道；可按「来源章节」「来源批次」筛选</li>
        </ol>
        <p style="color:#909399;font-size:13px;">
          来源批次 <code>batch:批次名</code> 表示从文档章节直接生成；与测试分析产生的批次不同。
        </p>

        <h4>二、测试分析（测试点 → 方案 → 用例）</h4>
        <p>路径：<strong>AI 测试 → 测试分析</strong>。与需求文档共用同一份上传文件，无需重复上传。</p>
        <ol>
          <li><strong>生成测试点</strong> → 按章节范围生成结构化测试点，支持思维导图、XMind 导出、批次管理</li>
          <li><strong>确认测试点</strong> → 列表中勾选后「确认选中」，方案与用例生成默认只纳入已确认项</li>
          <li><strong>生成测试方案</strong> → 输出 Markdown 方案，可填测试环境补充信息，支持预览、编辑、导出 Word</li>
          <li><strong>从测试点生成用例</strong> → 写入「需求用例」同一张表，来源标识为 <code>test_points:batch:批次名</code></li>
          <li><strong>复制到用例库</strong> → 测试点列表、整体视图、方案页或列表行「复制到库」，将工作区用例写入功能用例库（原工作区保留）</li>
          <li><strong>追溯与筛选</strong> → 在需求用例页按「测试点批次」筛选；用例行可点击「测试点 #id」跳回测试分析</li>
        </ol>
        <table class="help-table">
          <thead>
            <tr>
              <th>推荐顺序</th>
              <th>说明</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>上传需求</td>
              <td>在「需求用例生成」完成文档上传与解析</td>
            </tr>
            <tr>
              <td>测试分析</td>
              <td>测试点 → 确认 → 测试方案 → 从测试点生成功能用例</td>
            </tr>
            <tr>
              <td>需求用例页</td>
              <td>统一编辑、按来源筛选、导出禅道</td>
            </tr>
          </tbody>
        </table>

        <h4>三、功能用例库（项目级资产）</h4>
        <p>路径：<strong>AI 测试 → 功能用例库</strong>。与工作区（需求页临时用例）分离，适合长期维护与自动化选型。</p>
        <ol>
          <li><strong>复制入库</strong> → 在「需求用例生成」勾选工作区用例 →「导入到用例库」；<strong>复制</strong>而非移动，原需求侧数据保留</li>
          <li><strong>禅道 XLSX 导入</strong> → 上传平台导出格式的 Excel 回导；导入时<strong>不自动去重</strong></li>
          <li><strong>重复检验</strong> → 按「标题 + 模块」扫描重复组，人工勾选批量删除</li>
          <li><strong>筛选排序</strong> → 支持禅道 ID、来源、关键词；可按创建/修改时间、禅道 ID 排序</li>
          <li><strong>导出禅道</strong> → 勾选或按筛选导出 XLSX，列与平台导出模板一致</li>
        </ol>
        <p style="color:#909399;font-size:13px;">
          来源标识：<code>requirement_copy</code>（需求复制）、<code>zentao_xlsx</code>（禅道导入）、<code>manual</code>（手工新建）。
        </p>

        <h4>三-A、问答准确性评测（知识库 / RAG）</h4>
        <p>路径：<strong>AI 测试 → 问答准确性评测</strong>。对标线下 550 题 RAG 批量问答与总结报告。</p>
        <ol>
          <li><strong>评测集</strong>：下载 Excel 模板导入（问题、标准答案必填；序号、问答目录、多轮、问题类型等）</li>
          <li><strong>被测 API</strong>：配置 SSE 流式或 HTTP 问答接口，支持接口调试</li>
          <li><strong>执行评测</strong>：填写<strong>评测名称</strong>（默认评测集名，可在执行记录中识别）；模式：自动（API+LLM 评判）/ 仅评判 / 仅拉取；支持序号范围、失败重跑、自动分批（500+ 题）</li>
          <li><strong>报告</strong>：统计报告（优秀率/场景类型分析）、单题报告、人工审核、合并导出与迭代对比</li>
        </ol>
        <p style="color:#909399;font-size:13px;">评判模型在「AI 模型配置 → 场景绑定 → 问答准确性评判」；设计详见 <code>docs/设计文档/qa-eval-accuracy.md</code>。</p>

        <h4>四、AI 生成 API 测试用例</h4>
        <ol>
          <li>在「<strong>接口自动化 → 接口管理 / 用例管理</strong>」中选择接口，点击「AI 生成用例」</li>
          <li>弹窗内可选择<strong>AI 模型</strong>（不选则用默认配置）</li>
          <li>AI 根据接口定义与响应结构生成测试数据、断言、变量提取</li>
          <li>预览、编辑后一键导入为正式接口用例</li>
          <li>环境变量支持 <code v-pre>${{random_int}}</code>、Faker 表达式、前后置 Python 脚本（RestrictedPython 沙箱）</li>
        </ol>
        <p style="color:#909399;font-size:13px;">也可从「AI 工作台 → 接口 AI 生成」跳转至接口管理。</p>

        <h4>五、AI 生成 / 录制 UI 测试用例</h4>
        <p><strong>入口 A — Web 自动化模块</strong>（「Web 自动化 → 测试用例」→ 新增 → AI 生成 / 录制）</p>
        <ol>
          <li>填写测试描述（建议含账号、完整流程、预期结果）</li>
          <li>选择 <strong>AI 模型</strong> 与生成模式：单页面 / 多轮探索（推荐）</li>
          <li><strong>录制</strong>：Runner 弹出浏览器，手动操作后停止；可再「AI 优化步骤」</li>
          <li>编辑步骤后保存；UI 用例可展示来源功能用例（若从库导入）</li>
        </ol>
        <p><strong>入口 B — 功能用例库 → UI 闭环（推荐）</strong></p>
        <ol>
          <li>在「功能用例库」勾选 1～10 条功能用例</li>
          <li><strong>生成 UI 自动化</strong>：配置目标 URL、AI 模型；系统按「标题 + 前置 + 步骤」拼装描述，逐条 AI 生成步骤 → 预览 → 导入 <code>case</code> 表</li>
          <li><strong>录制 UI 自动化</strong>：配置起始 URL；Runner 打开页面后手动登录并操作业务步骤 → 停止 → 可选 AI 优化 → 导入 UI 用例库</li>
          <li>列表「UI 状态」列显示：未生成 / 已生成 / 已导入；可跳转编辑已导入的 UI 用例</li>
        </ol>

        <h4>六、录制与 AI 优化（UI）</h4>
        <table class="help-table">
          <thead>
            <tr><th>能力</th><th>说明</th></tr>
          </thead>
          <tbody>
            <tr><td>悬浮录制</td><td>鼠标悬停菜单/下拉项可配置停留时间（500ms～5s）后写入步骤</td></tr>
            <tr><td>AI 优化</td><td>录制完成后可选模型，补全步骤描述、合并冗余操作、补充断言</td></tr>
            <tr><td>测试描述</td><td>建议「操作 + → 预期：」：只在登录成功、查询结果、保存成功等节点写预期；预期用页面真实文案（菜单名、列表数据、提示语），勿写「输入框可见」。勾选补充断言时尤其要写明预期</td></tr>
            <tr><td>断言 placement</td><td>优化时可指定断言插在相关操作<strong>之前</strong>或<strong>之后</strong></td></tr>
            <tr><td>否定断言</td><td>支持「元素不存在 / 不可见 / 隐藏」类断言（如校验弹窗关闭、列表无重复项）</td></tr>
            <tr><td>登录说明</td><td>录制模式一般不自动登录；在浏览器中手动登录后操作，或在测试描述中补充账号信息供 AI 优化</td></tr>
          </tbody>
        </table>

        <h4>探索模式详解（UI AI 生成）：</h4>
        <table class="help-table">
          <thead>
            <tr>
              <th>特性</th>
              <th>说明</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>多轮生成</td>
              <td>每轮 AI 抓取当前页面 DOM 并生成步骤，执行后检测页面变化，进入下一轮。轮次可调（1-10）</td>
            </tr>
            <tr>
              <td>登录态保持</td>
              <td>同一浏览器上下文内执行，登录后的 Cookie/Session 自动保留，后续步骤无需重新登录</td>
            </tr>
            <tr>
              <td>弹窗处理</td>
              <td>自动识别并关闭遮罩层、抽屉、Cookie 同意框等干扰元素</td>
            </tr>
            <tr>
              <td>DOM 稳定等待</td>
              <td>页面变化后自动等待 DOM 稳定（SPA 动态加载适配），避免抓取到半渲染状态</td>
            </tr>
            <tr>
              <td>失败保留</td>
              <td>某步执行失败时不丢弃已生成步骤，自动截图保存现场，方便排查定位问题</td>
            </tr>
            <tr>
              <td>自动截图</td>
              <td>每轮开始、页面变化、执行失败时自动截图，生成过程可视化</td>
            </tr>
          </tbody>
        </table>

        <h4>全流程对照（推荐顺序）：</h4>
        <table class="help-table">
          <thead>
            <tr><th>阶段</th><th>页面</th><th>产出</th></tr>
          </thead>
          <tbody>
            <tr><td>1. 上传需求</td><td>需求用例生成</td><td>章节树、工作区功能用例（草稿）</td></tr>
            <tr><td>2. 测试分析</td><td>测试分析</td><td>测试点、测试方案、导图/XMind</td></tr>
            <tr><td>3. 生成用例</td><td>测试分析 / 需求页</td><td>写入工作区 <code>ai_requirement_case</code></td></tr>
            <tr><td>4. 入库治理</td><td>功能用例库</td><td>复制入库、禅道导入、重复检验</td></tr>
            <tr><td>5. UI 自动化</td><td>功能用例库 / Web 用例</td><td>AI 生成或录制 → 导入 Playwright 步骤</td></tr>
            <tr><td>6. 接口自动化</td><td>接口管理</td><td>AI 生成 API 用例（可选，与功能用例并行）</td></tr>
          </tbody>
        </table>

        <h4>描述撰写建议：</h4>
        <ul>
          <li><strong>包含账号密码</strong>：如「使用账号 test@example.com / 密码 123456 登录」</li>
          <li><strong>说明完整流程</strong>：如「登录后进入控制台，点击新增按钮，填写名称和描述，保存后验证列表出现新数据」</li>
          <li><strong>指定目标页面</strong>：提供起始 URL，如 https://kbs-test.apps.xxx.com/login</li>
          <li><strong>说明预期结果</strong>：让 AI 知道最后一步应该验证什么</li>
        </ul>

        <h4>AI 失败分析（已上线）</h4>
        <p>接口 / UI 执行失败后，可在执行详情页一键分析根因；UI 失败默认尝试 Vision 读取失败步骤截图。</p>
        <ul>
          <li><strong>入口</strong>：接口执行详情、UI 用例执行记录、套件报告页 → 失败行「AI 分析」</li>
          <li><strong>权限</strong>：<code>ai_test:execute</code></li>
          <li><strong>输出</strong>：根因、可能原因、修复建议、错误分类、置信度</li>
          <li><strong>Vision</strong>：UI 有截图且已配置 qwen-vl / gpt-4o 等模型时自动读图；抽屉内可切换模型</li>
          <li><strong>缓存</strong>：24h 内同记录返回缓存，可「重新分析」刷新</li>
          <li><strong>报告摘要</strong>：套件/计划/接口执行详情页顶部「AI 报告摘要」卡片</li>
          <li><strong>批量分析</strong>：报告页「批量 AI 分析失败」一次分析 Top 5 失败用例</li>
          <li><strong>工作台</strong>：「最近失败 · AI 分析」列表快捷入口</li>
        </ul>

        <h4>注意事项：</h4>
        <ul>
          <li><strong>需求 / 功能用例</strong>：生成质量依赖模型与 Prompt，高优先级场景务必人工复核；大文档请分章节多次生成</li>
          <li><strong>含图章节</strong>：务必配置 Vision 模型；仅标题+截图的章节建议勾选相邻有正文的章节</li>
          <li><strong>功能用例库</strong>：禅道导入允许重复，定期使用「重复检验」清理；转 UI 单次建议 ≤10 条（串行 AI，耗时较长）</li>
          <li><strong>录制</strong>：需 Windows 执行器已上线，或开发模式启动 <code>runner/main.py</code>；录制不会自动写登录步骤，复杂登录请先手动完成</li>
          <li><strong>接口 / UI 执行用例</strong>：AI 结果供参考，断言与选择器需人工确认；探索模式轮次越多耗时越长（每轮约 10～20 秒）</li>
          <li>复杂 UI 流程建议拆成多条功能用例，再分别生成/录制 UI 用例</li>
        </ul>

        <h4>规划中的能力（尚未上线）：</h4>
        <ul>
          <li>AI 生成测试报告文字摘要</li>
          <li>Vision 模型直接参与 UI 步骤生成（截图理解，与失败分析读图不同）</li>
          <li>功能用例 → 接口用例批量生成</li>
          <li>SSE 流式展示 AI 思考过程（当前为整段返回）</li>
        </ul>
      </div>

      <el-divider />

      <div class="help-section">
        <h3>📁 1. 项目管理</h3>
        <p>项目是所有测试的容器，建议按业务系统或产品划分项目。</p>
        <ul>
          <li>点击「项目管理」→「新增项目」创建新项目</li>
          <li>填写项目名称和描述，方便识别</li>
          <li>切换项目：点击顶部下拉框选择当前工作项目</li>
        </ul>
      </div>

      <el-divider />

      <div class="help-section">
        <h3>🏢 2. 测试环境</h3>
        <p>环境配置用于管理不同环境的网址（如测试环境、预发布环境）。</p>
        <ul>
          <li>点击「测试环境」→「新增环境」</li>
          <li>输入环境名称（如：测试环境）和基础 URL</li>
          <li>执行测试时选择对应环境即可</li>
        </ul>
      </div>

      <el-divider />

      <div class="help-section">
        <h3>🖥️ BrickCore 执行器（Runner 客户端）</h3>
        <p>
          Web UI 自动化、AI 录制与定时任务依赖本机或服务器上的 <strong>执行器</strong>。
          Windows 测试人员请使用打包好的 <strong>BrickCoreRunner</strong> 桌面程序；Linux CI 可运行无头 <code>runner/main.py</code>。
        </p>
        <h4>获取与安装（Windows）：</h4>
        <ol>
          <li>进入 <strong>UI 自动化 → 设备管理</strong>，选择 <strong>网盘下载</strong> 或 <strong>平台下载 zip</strong>（网盘链接由管理员在 <strong>系统管理 → 执行器发布</strong> 配置）</li>
          <li>解压后运行 <code>BrickCoreRunner.exe</code>，默认连接线上平台地址</li>
          <li>使用平台账号登录 → 填写设备名称 → 点击 <strong>上线</strong></li>
          <li>设备列表出现 <strong>在线</strong> 后，即可运行用例、AI 录制、查看实时画面</li>
        </ol>
        <h4>设备管理增强：</h4>
        <ul>
          <li>列表展示 <strong>客户端版本</strong>、<strong>最后心跳</strong>，可 <strong>复制设备编号</strong>（执行计划 / 小测助手填 device_id 时用）</li>
          <li>安装包未上传时，页面会提示管理员将 zip 放到 <code>static/runner/</code></li>
        </ul>
        <h4>检查更新：</h4>
        <ul>
          <li>客户端窗口 <strong>检查更新</strong> 可对比平台版本并 <strong>下载安装包</strong> 到「下载」文件夹</li>
          <li>关闭客户端后解压新 zip 覆盖原目录（整包升级最稳妥）</li>
        </ul>
        <p style="color:#909399;font-size:13px;">
          详细说明见帮助中心：<strong>执行器使用说明</strong>、<strong>执行器打包说明</strong>、<strong>Linux 无头 Runner</strong>。
        </p>
      </div>

      <el-divider />

      <div class="help-section">
        <h3>📦 3. 测试模块</h3>
        <p>模块用于对测试用例进行分类管理（如：登录模块、订单模块）。</p>
        <ul>
          <li>点击「测试模块」→「新增模块」创建模块</li>
          <li>编写用例时选择归属模块</li>
          <li>模块只是分类，不影响测试执行</li>
        </ul>
      </div>

      <el-divider />

      <div class="help-section">
        <h3>📝 4. 测试用例（核心）</h3>
        <p>用例是自动化测试的基本单位，通过拖拽方式编排测试步骤。</p>
        
        <h4>创建用例：</h4>
        <ol>
          <li>点击「测试用例」→「新增用例」</li>
          <li>填写用例名称、选择模块和环境</li>
          <li>从右侧拖拽操作步骤到编辑区</li>
        </ol>

        <h4>常用操作说明：</h4>
        <table class="help-table">
          <thead>
            <tr>
              <th>操作</th>
              <th>说明</th>
              <th>示例</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>打开网页</td>
              <td>访问指定网址</td>
              <td>https://www.example.com</td>
            </tr>
            <tr>
              <td>点击元素</td>
              <td>点击页面上的按钮/链接</td>
              <td>#login-btn（CSS选择器）</td>
            </tr>
            <tr>
              <td>输入文本</td>
              <td>在输入框中输入内容</td>
              <td>用户名、密码</td>
            </tr>
            <tr>
              <td>等待</td>
              <td>暂停指定时间（秒）</td>
              <td>2（等待2秒）</td>
            </tr>
            <tr>
              <td>断言</td>
              <td>验证页面元素或文本</td>
              <td>检查是否包含"登录成功"</td>
            </tr>
          </tbody>
        </table>

        <h4>元素定位方式：</h4>
        <ul>
          <li><strong>CSS选择器</strong>：#id、.class、tag（推荐）</li>
          <li><strong>XPath</strong>：//div[@class='btn']</li>
          <li><strong>文本</strong>：button:has-text("提交")</li>
        </ul>

        <h4>变量引用：</h4>
        <ul>
          <li>步骤参数（如输入框 value、定位器中的动态文本）使用 <code v-pre>${{变量名}}</code></li>
          <li>环境变量：<code v-pre>${{username}}</code>、<code v-pre>${{password}}</code></li>
          <li>随机值：<code v-pre>auto_${{random_int}}</code>；提取变量后引用：<code v-pre>${{token}}</code></li>
        </ul>
      </div>

      <el-divider />

      <div class="help-section">
        <h3>📚 5. 测试套件</h3>
        <p>套件用于批量执行多个测试用例。</p>
        <ul>
          <li>点击「测试套件」→「新增套件」</li>
          <li>从左侧选择要组合的用例，添加到右侧</li>
          <li>保存后可直接执行整个套件</li>
        </ul>
      </div>

      <el-divider />

      <div class="help-section">
        <h3>📅 6. UI 测试计划（任务计划）</h3>
        <p>用于 UI 自动化场景：将多个测试套件组合为任务计划，并配合「定时任务」自动执行。</p>
        <ul>
          <li>在「Web 自动化」中创建计划并关联套件</li>
          <li>在「定时任务」中配置 Cron / 固定间隔触发</li>
          <li>执行完成后可查看任务报告与截图</li>
        </ul>
        <p style="color:#909399;font-size:13px;">接口侧的「测试计划」见下方「接口自动化测试」章节，用于编排 API 套件与单条用例。</p>
      </div>

      <el-divider />

      <div class="help-section">
        <h3>⏰ 7. 定时任务</h3>
        <p>查看和管理所有定时执行的计划任务。</p>
        <ul>
          <li>启动/暂停定时任务</li>
          <li>查看下次执行时间</li>
          <li>查看任务执行历史</li>
        </ul>
      </div>

      <el-divider />

      <div class="help-section">
        <h3>📊 8. 执行记录</h3>
        <p>查看所有测试的执行历史和结果（UI 与接口分模块展示）。</p>
        <ul>
          <li><strong>UI</strong>：绿色 = 通过，红色 = 失败；可查看步骤日志与截图</li>
          <li><strong>接口</strong>：「接口自动化 → 执行记录」统一查看套件/计划记录</li>
          <li>支持报告页、导出 HTML、发送邮件；列表展示执行总耗时与接口总耗时</li>
        </ul>
      </div>

      <el-divider />

      <div class="help-section">
        <h3>🌐 接口自动化测试</h3>
        <p>本平台同时支持 HTTP/HTTPS 接口的自动化测试，适用于 RESTful API、微服务接口等场景。</p>
        
        <h4>基本流程：</h4>
        <ol>
          <li><strong>导入接口</strong> → Swagger/Postman 导入或手动创建（支持 form-data 文件字段）</li>
          <li><strong>编写用例</strong> → 配置请求、断言、变量提取、前置/后置脚本</li>
          <li><strong>组建套件</strong> → 按业务场景组合用例，支持变量传递与失败即停</li>
          <li><strong>测试计划</strong> → 编排多个套件或单用例，串行/并行执行</li>
          <li><strong>定时任务</strong> → 对套件或计划配置 Interval / Date / Crontab</li>
          <li><strong>查看报告</strong> → 执行记录中查看详情、导出 HTML、发送邮件</li>
          <li><strong>数据工厂</strong> → 管理数据源与 SQL 模板，套件/用例级库断言与 setup/teardown</li>
        </ol>

        <h4>数据工厂（P1）：</h4>
        <ol>
          <li><strong>数据源</strong> → 「接口自动化 → 数据工厂」配置 MySQL 等连接（按环境隔离）；<strong>密码 Fernet 加密存储</strong>，不回显明文</li>
          <li><strong>保存</strong> → 新建必填密码；编辑留空不修改；弹窗「测试连接」不落库，测试通过后须点「保存」</li>
          <li><strong>SQL 模板</strong> → 维护 setup/teardown 脚本，支持 <code v-pre>${{变量}}</code> 替换</li>
          <li><strong>用例级断言</strong> → 用例编辑页「数据库断言」可调试后保存</li>
          <li><strong>套件级</strong> → 接口套件 / UI 套件可配置前置 SQL、后置 SQL 与套件级库断言</li>
          <li><strong>执行时机</strong> → 接口：setup 在用例前、teardown+断言在用例后；UI：setup 在派发前、teardown+断言在 Runner 完成后回调</li>
        </ol>

        <h4>接口管理功能：</h4>
        <table class="help-table">
          <thead>
            <tr>
              <th>功能</th>
              <th>说明</th>
              <th>使用场景</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>接口导入</td>
              <td>支持 Swagger/OpenAPI、Postman、Curl 导入</td>
              <td>快速迁移已有接口文档</td>
            </tr>
            <tr>
              <td>关联用例</td>
              <td>接口列表展示引用数，抽屉内编辑或跳转用例管理</td>
              <td>接口变更后批量维护用例</td>
            </tr>
            <tr>
              <td>响应示例</td>
              <td>支持 JSON 或 SSE 等多行原始文本，供 AI/Schema 参考</td>
              <td>流式接口、非 JSON 响应的断言辅助</td>
            </tr>
            <tr>
              <td>接口用例</td>
              <td>基于接口创建测试用例，配置参数和断言</td>
              <td>验证接口功能是否正常</td>
            </tr>
            <tr>
              <td>变量提取</td>
              <td>从响应中提取数据供后续用例使用</td>
              <td>接口依赖场景（如 Token 传递）</td>
            </tr>
            <tr>
              <td>断言规则</td>
              <td>支持状态码、JSON 路径、响应头等多种断言</td>
              <td>验证接口返回是否符合预期</td>
            </tr>
            <tr>
              <td>接口套件</td>
              <td>按业务场景组织多个接口用例，顺序执行并传递变量；添加时可按 P0～P3 筛选</td>
              <td>登录 → 下单 → 查询等流程测试</td>
            </tr>
            <tr>
              <td>测试计划</td>
              <td>组合多个套件或单条用例，支持串行/并行与 item 依赖</td>
              <td>回归测试、多模块串联、冒烟巡检</td>
            </tr>
            <tr>
              <td>定时任务</td>
              <td>对套件或计划配置 Interval / Date / Crontab 调度</td>
              <td>持续集成、接口监控、夜间巡检</td>
            </tr>
            <tr>
              <td>执行记录</td>
              <td>查看套件/计划/单用例历史，支持报告页、导出、邮件推送</td>
              <td>问题追溯、结果归档</td>
            </tr>
            <tr>
              <td>数据工厂</td>
              <td>数据源（密码密文存储）、SQL 模板、库断言；HTML 报告展示 hooks 结果</td>
              <td>造数、清数、DB 校验与接口/UI 联动</td>
            </tr>
            <tr>
              <td>前置/后置脚本</td>
              <td>Python 受限沙箱（RestrictedPython），可读写 variables；后置可读 response</td>
              <td>分页参数注入、从列表响应提取 id 传给下游用例</td>
            </tr>
            <tr>
              <td>Form-data 上传</td>
              <td>接口与用例支持 multipart 文件字段</td>
              <td>文件上传接口测试</td>
            </tr>
          </tbody>
        </table>

        <h4>测试计划使用说明：</h4>
        <ul>
          <li>在「接口自动化 → 测试计划」中新建计划，添加<strong>套件</strong>或<strong>单条用例</strong>作为执行条目</li>
          <li><strong>串行</strong>：按顺序执行，前序条目提取的变量可传递给后续用例</li>
          <li><strong>并行</strong>：各条目独立执行（适合无依赖的巡检场景）</li>
          <li>可为条目配置<strong>依赖</strong>：仅当前置条目成功时才执行</li>
          <li>列表操作：<strong>执行</strong>立即运行（后台异步，可关闭弹窗后在执行记录查看）、<strong>编辑</strong>维护内容、<strong>报告</strong>查看历史执行、<strong>删除</strong>移除计划</li>
        </ul>

        <h4>执行报告与耗时说明：</h4>
        <ul>
          <li><strong>接口总耗时</strong>（绿色）：各用例纯 HTTP 网络时间之和，用于评估接口性能</li>
          <li><strong>执行总耗时</strong>：含用例加载、断言、变量提取、脚本及平台调度开销</li>
          <li>单条用例同时展示「接口耗时」与「用例总耗时」；报告支持阶段耗时分解（HTTP 请求、断言等）</li>
          <li>执行记录列表提供「执行总耗时」与「接口总耗时」两列，便于快速对比</li>
        </ul>

        <h4>变量语法说明（UI / 接口自动化统一使用 <code v-pre>${{变量名}}</code>）：</h4>
        <ul>
          <li><strong>基础变量</strong>：<code v-pre>${{变量名}}</code> - 从环境、前置脚本或上游用例提取的变量</li>
          <li><strong>随机数</strong>：<code v-pre>${{random_int}}</code> - 随机整数（默认 1000–9999）；环境变量可配置 <code>faker.random_int(min=100,max=100000)</code></li>
          <li><strong>时间戳</strong>：<code v-pre>${{now_time}}</code> - 当前时间；<code v-pre>${{today}}</code> - 当前日期</li>
          <li><strong>同用例内一致</strong>：同一用例多次引用 <code v-pre>${{random_int}}</code> 值相同；套件内不同用例会重新生成</li>
          <li><strong>跨用例传递</strong>：用例 1 提取/后置脚本设置的变量（如 token）会自动传给套件后续用例</li>
          <li><strong>嵌套示例</strong>：<code>{"tag_name": "标签_${{random_int}}"}</code>，引用 <code v-pre>${{tag_name}}</code> → <code>标签_4829</code></li>
        </ul>

        <h4>前后置脚本说明（接口用例）：</h4>
        <ul>
          <li><strong>语言</strong>：Python（RestrictedPython 受限沙箱，非完整 Python）</li>
          <li><strong>前置脚本</strong>：请求发送前执行，写入 <code>variables</code>，供 Params/Body 中 <code v-pre>${{变量名}}</code> 引用</li>
          <li><strong>后置脚本</strong>：响应返回后执行，从 <code>response['body']</code> 提取字段写入 <code>variables</code>，套件内后续用例可引用</li>
          <li><strong>可用函数</strong>：<code>print()</code>、<code>timestamp()</code>（Unix 时间戳）</li>
          <li><strong>不可用</strong>：<code>__import__</code>、<code>import os</code>、<code>open()</code> 等</li>
          <li>执行报告「请求详情」→ <strong>script_logs</strong> 可查看脚本输出</li>
        </ul>

        <h4>Cron 表达式示例：</h4>
        <ul>
          <li><code>0 */5 * * * *</code> - 每 5 分钟执行一次</li>
          <li><code>0 0 9 * * *</code> - 每天上午 9 点执行</li>
          <li><code>0 0 9 * * 1-5</code> - 工作日（周一至周五）上午 9 点执行</li>
          <li><code>0 0 0 * * 0</code> - 每周日凌晨执行</li>
        </ul>
      </div>

      <el-divider />

      <div class="help-section">
        <h3>🔐 Token 授权（接口登录态）</h3>
        <p><strong>路径</strong>：接口自动化 → Token 授权。执行用例/套件/计划前自动注入 <code v-pre>${{token}}</code> 等变量，过期时按配置自动刷新。</p>

        <h4>何时需要 / 不需要：</h4>
        <ul>
          <li><strong>不需要</strong>：Token 已写在环境 <code>global_vars</code> 中 → 用例直接写 <code v-pre>${{变量名}}</code></li>
          <li><strong>需要</strong>：需定期登录刷新、同一环境多套角色 Token、从登录接口动态提取</li>
        </ul>

        <h4>推荐配置（接口登录）：</h4>
        <ol>
          <li>新建授权，选择 <strong>环境</strong>（与顶部项目下的环境列表一致）</li>
          <li>选择 <strong>登录接口</strong>（须能在接口管理调试成功）</li>
          <li>配置 <strong>变量提取</strong>（JSON / Header / 正则），如 <code>token</code> ← <code>$.data.token</code></li>
          <li>点击 <strong>调试授权</strong> 预览提取结果 → 保存 → 列表 <strong>刷新</strong> 写入缓存</li>
          <li>用例请求头：<code v-pre>Authorization: Bearer ${{token}}</code>（注意 Bearer 后空格）</li>
        </ol>

        <h4>高级选项 — 自定义代码：</h4>
        <p style="color:#909399;font-size:13px;">展开对话框「高级选项」可切换。仅适合从环境变量拼 Token 或固定值，<strong>不能发 HTTP</strong>；多步登录请用接口登录。</p>

        <h4>列表操作：</h4>
        <ul>
          <li><strong>刷新</strong>：立即重新登录并更新缓存</li>
          <li><strong>缓存</strong>：查看当前 token 等字段与过期时间</li>
          <li><strong>清空</strong>：清除缓存，下次执行会重新登录</li>
        </ul>

        <h4>变量优先级（同名变量谁生效）：</h4>
        <p>合并顺序（低→高）：项目全局变量 → 环境变量 → 套件前序用例提取 → <strong>Token 授权</strong> → 前置脚本。</p>
        <ul>
          <li><strong>Token 授权会覆盖</strong> 环境变量及套件传递的同名 token</li>
          <li>套件「登录用例 extract」与 Token 授权请 <strong>二选一</strong>，不要两处都配同名 <code>token</code></li>
          <li>多角色用不同变量名（如 <code v-pre>admin_token</code> / <code v-pre>user_token</code>）；同一环境仅一条授权可启用</li>
          <li>固定 Token 可只写在环境 <code>global_vars</code>，不必建授权</li>
        </ul>
      </div>

      <el-divider />

      <div class="help-section">
        <h3>🔌 Mock 服务（接口模拟）</h3>
        <p>Mock 服务用于模拟后端接口返回，当前端或第三方系统调用 Mock 地址时，平台会按预设规则返回固定响应。适用于后端接口尚未开发完成时的前端联调、异常场景测试等。</p>

        <h4>使用步骤：</h4>
        <ol>
          <li><strong>创建 Mock</strong> → 「接口自动化 > Mock 服务」→ 点击「新建 Mock」</li>
          <li><strong>配置匹配规则</strong> → 填写请求方法（GET/POST/...）和匹配路径（如 <code>/api/users</code>）</li>
          <li><strong>配置响应</strong> → 设置状态码、响应 Body、Headers、延迟时间（ms）</li>
          <li><strong>启用并调用</strong> → 保存后开启启用开关，通过调用地址访问即可拿到模拟响应</li>
        </ol>

        <h4>调用地址格式：</h4>
        <pre style="background:#f5f7fa;padding:10px;border-radius:4px;font-size:13px">{{ baseUrl }}/api-module/mock-call/你的匹配路径

# 示例：
GET  {{ baseUrl }}/api-module/mock-call/api/users
POST {{ baseUrl }}/api-module/mock-call/api/login</pre>

        <h4>高级匹配规则（可选）：</h4>
        <table class="help-table">
          <thead>
            <tr>
              <th>规则类型</th>
              <th>说明</th>
              <th>示例</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Header 匹配</td>
              <td>请求头必须包含指定键值才命中</td>
              <td><code>{"header": {"Authorization": "Bearer xxx"}}</code></td>
            </tr>
            <tr>
              <td>Query 匹配</td>
              <td>URL 查询参数必须匹配</td>
              <td><code>{"query": {"type": "1"}}</code></td>
            </tr>
            <tr>
              <td>Body 匹配</td>
              <td>请求体 JSON 顶层字段必须匹配（仅 POST/PUT/PATCH）</td>
              <td><code>{"body": {"user_id": 1}}</code></td>
            </tr>
          </tbody>
        </table>

        <h4>功能特性：</h4>
        <ul>
          <li><strong>响应延迟</strong>：可设置 0~60000ms 延迟，模拟弱网或慢接口</li>
          <li><strong>调用统计</strong>：每次命中自动累加「调用次数」并记录「最后调用时间」</li>
          <li><strong>启用/禁用</strong>：通过开关快速控制 Mock 是否生效，无需删除</li>
          <li><strong>多项目隔离</strong>：Mock 按项目归属，不同项目可配置相同路径互不干扰</li>
        </ul>

        <h4>典型使用场景：</h4>
        <ul>
          <li><strong>前端联调</strong>：后端接口还没写好，前端先调 Mock 地址，不阻塞开发进度</li>
          <li><strong>异常测试</strong>：配置返回 500 或超时的 Mock，测试前端容错和兜底逻辑</li>
          <li><strong>依赖隔离</strong>：测试 A 服务时，B 服务未部署，用 Mock 顶替 B 的响应</li>
        </ul>
      </div>

      <el-divider />

      <div class="help-section">
        <h3>⚡ 9. 性能测试</h3>
        <p>基于已有 API 用例快速发起压测，无需编写脚本。支持三种压测模式，自动采集并生成聚合报告。</p>

        <h4>使用步骤：</h4>
        <ol>
          <li><strong>准备用例</strong> → 在「接口自动化 → 用例管理」中创建 API 用例（配置请求 + 断言）</li>
          <li><strong>创建场景</strong> → 在「性能测试 → 场景管理」中新建场景，选择用例并配置压测参数</li>
          <li><strong>执行压测</strong> → 选择执行环境，点击「执行」按钮启动压测</li>
          <li><strong>查看报告</strong> → 在「性能测试 → 执行记录」中点击「报告」查看详细结果</li>
        </ol>

        <h4>三种压测模式：</h4>
        <table class="help-table">
          <thead>
            <tr>
              <th>模式</th>
              <th>说明</th>
              <th>适用场景</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>固定模式</td>
              <td>固定并发数，持续指定时间</td>
              <td>标准压力测试，如 10 并发持续 60 秒</td>
            </tr>
            <tr>
              <td>循环模式</td>
              <td>固定并发数，每个用户循环指定次数</td>
              <td>固定总量测试，如 10 并发各执行 100 次</td>
            </tr>
            <tr>
              <td>梯度模式</td>
              <td>分阶段递增并发，每阶段持续指定时间</td>
              <td>容量测试，逐步加压找到性能拐点</td>
            </tr>
          </tbody>
        </table>

        <h4>配置说明：</h4>
        <ul>
          <li><strong>并发用户数</strong>：同时发起请求的虚拟用户数（1-200）</li>
          <li><strong>Ramp-up 时间</strong>：从 0 用户到目标并发数的渐进加压时间</li>
          <li><strong>用例权重</strong>：多个用例时，按权重比例随机选择执行</li>
          <li><strong>请求间隔</strong>：每次请求后的等待时间（毫秒），模拟真实用户思考时间</li>
        </ul>

        <h4>报告指标解读：</h4>
        <ul>
          <li><strong>QPS</strong>：每秒查询数，系统吞吐量的核心指标</li>
          <li><strong>Avg / Median / P90 / P95 / P99 RT</strong>：平均/中位数/百分位响应时间，P95 表示 95% 的请求响应时间低于该值</li>
          <li><strong>StdDev</strong>：响应时间标准差，越大说明响应越不稳定</li>
          <li><strong>Received/Sent KB/s</strong>：每秒接收/发送的数据量</li>
          <li><strong>错误分类</strong>：按错误类型和状态码分类统计失败请求</li>
        </ul>

        <h4>注意事项：</h4>
        <ul>
          <li>压测目标建议仅对测试环境执行，避免影响生产服务</li>
          <li>性能测试复用接口用例的变量替换和断言逻辑，但不做跨请求变量传递</li>
          <li>压测过程中可随时点击「停止」终止执行</li>
        </ul>
      </div>

      <el-divider />

      <div class="help-section">
        <h3>🔔 10. 通知告警</h3>
        <p>支持执行失败告警和测试报告自动推送。</p>
        <ul>
          <li><strong>通知配置</strong>：每个项目独立配置接收人和渠道（邮件/钉钉/企微）</li>
          <li><strong>SMTP 配置</strong>：全局邮件服务器设置，用于发送邮件通知</li>
          <li><strong>自动推送</strong>：API 套件/计划与 UI 计划执行完成后可自动发送 HTML 报告</li>
          <li><strong>失败告警</strong>：用例执行失败时自动发送告警通知</li>
          <li><strong>推送记录</strong>：在「系统管理 → 推送记录」中查看所有发送记录和状态</li>
        </ul>
      </div>

      <el-divider />

      <div class="help-section">
        <h3>🛡️ 11. 系统管理</h3>
        <p>平台管理功能，仅管理员可见。</p>
        <ul>
          <li><strong>用户管理</strong>：管理系统用户，启用/禁用账号</li>
          <li><strong>角色权限</strong>：配置角色和权限，实现菜单/按钮级权限控制</li>
          <li><strong>操作日志</strong>：记录关键操作（含 AI 测试、性能测试模块分类），支持敏感字段脱敏</li>
          <li><strong>通知配置 / SMTP 配置 / 推送记录</strong>：管理通知相关配置</li>
        </ul>
      </div>

      <el-divider />

      <div class="help-section">
        <h3>💡 使用技巧</h3>
        <ul>
          <li><strong>复制用例</strong>：编辑用例时点击「复制」快速创建相似用例</li>
          <li><strong>变量使用</strong>：用 <code v-pre>${{变量名}}</code> 实现数据驱动测试</li>
          <li><strong>iframe 处理</strong>：先切换 frame 再操作内部元素</li>
          <li><strong>接口调试</strong>：在接口管理或用例中「调试/send」通过后再加入套件/计划（单次调试默认超时 30 秒）</li>
          <li><strong>失败定位</strong>：执行结果中查看请求详情、响应 Body、断言与重试历史</li>
          <li><strong>性能关注</strong>：看「接口总耗时」判断接口快慢，勿与「执行总耗时」混淆</li>
          <li><strong>压测对比</strong>：多次执行同一场景，对比不同并发下的 QPS/RT 变化</li>
        </ul>
      </div>

      <el-divider />

      <div class="help-section">
        <h3>❓ 常见问题</h3>
        
        <h4>Q1: 元素定位失败怎么办？</h4>
        <p>A: 检查元素是否在 iframe 中，或使用了动态 id。建议使用 CSS 类名或 data-testid 属性。</p>

        <h4>Q2: 用例执行超时？</h4>
        <p>A: 网络较慢时，在步骤前添加「等待」操作，或增加隐式等待时间。</p>

        <h4>Q3: 如何参数化测试数据？</h4>
        <p>A: 在步骤参数或请求 URL/Header/Body 中使用 <code v-pre>${{变量名}}</code>；数据驱动场景在套件、数据集或 CSV 参数化中配置数据行。</p>

        <h4>Q4: 定时任务没执行？</h4>
        <p>A: 检查任务是否已启用，以及执行器服务是否正常运行。</p>

        <h4>Q5: 接口用例变量提取失败？</h4>
        <p>A: 检查 JSON Path 表达式是否正确，可使用在线工具验证。注意响应 Content-Type 应为 application/json。</p>

        <h4>Q6: 接口断言失败但实际结果正确？</h4>
        <p>A: 检查断言类型是否选择正确（如 JSON Path vs 包含），以及预期值的类型（字符串 vs 数字）。</p>

        <h4>Q7: 如何实现接口间的参数传递？</h4>
        <p>A: 在上一接口用例中配置「变量提取」，在下一接口用例中使用 <code v-pre>${{变量名}}</code> 引用。</p>

        <h4>Q8: 性能测试压测结果误差大？</h4>
        <p>A: 检查目标服务是否有缓存预热，建议预热后再压测。Ramp-up 时间建议 ≥ 并发数，避免瞬时高压。</p>

        <h4>Q9: 性能测试执行后没有报告数据？</h4>
        <p>A: 检查场景用例是否选择了正确的环境，以及接口是否可正常访问。查看推送记录确认是否有异常。</p>

        <h4>Q10: 报告里「执行总耗时」和「接口总耗时」为什么差很多？</h4>
        <p>A: 「接口总耗时」仅统计 HTTP 请求网络时间之和；「执行总耗时」还包含断言、变量提取、脚本、重试等待及平台加载/写库等开销。分析接口性能时请优先看接口耗时。</p>

        <h4>Q11: form-data 上传用例执行后响应是 base64？</h4>
        <p>A: 部分测试服务（如 httpbin）会将上传文件以 base64 形式回显在 JSON 中，属于对方接口的展示方式，不代表平台处理异常。</p>

        <h4>Q12: Token 授权环境下拉为空？</h4>
        <p>A: 先在顶部选择项目，并在「项目配置 → 环境」创建环境；授权页与项目环境共用同一列表。</p>

        <h4>Q13: 接口 401 但 Token 授权已配置？</h4>
        <p>A: 用「调试授权」确认变量已提取；检查用例是否选对环境；请求头是否为 <code v-pre>Bearer ${{token}}</code>（Bearer 与 token 之间有空格）；授权是否启用且缓存未过期。</p>

        <h4>Q14: 套件里登录用例 extract 了 token，为什么后面用例还是用不对？</h4>
        <p>A: 若同时启用了 <strong>Token 授权</strong> 且变量同名（如都叫 <code>token</code>），授权会在每条用例执行前覆盖套件传递的值。请关闭 Token 授权改走套件链式登录，或去掉套件登录用例、只用 Token 授权。详见 Token 授权页的「变量优先级」说明。</p>
      </div>

      <el-divider />

      <div class="help-footer">
        <p>📧 遇到问题？请联系系统管理员或查看接口文档获取更多技术支持。</p>
        <p style="color: #999; font-size: 12px;">版本：v1.5.0 | 更新日期：2026-06-01</p>
      </div>
    </el-scrollbar>
  </div>
</template>

<script setup>
import { computed } from 'vue'

defineProps({
  isHelpFullscreen: {
    type: Boolean,
    default: false
  }
})

const baseUrl = computed(() => {
  const envApi = import.meta.env.VITE_BASE_API || ''
  if (envApi.startsWith('http')) return envApi
  return window.location.origin + envApi
})
</script>

<style scoped>
.help-content {
  padding: 0 10px;
}

.help-section {
  margin-bottom: 20px;
}

.help-section h3 {
  color: #409EFF;
  margin-bottom: 15px;
  font-size: 18px;
}

.help-section h4 {
  color: #333;
  margin: 15px 0 10px;
  font-size: 15px;
}

.help-section p {
  line-height: 1.8;
  color: #666;
  margin-bottom: 10px;
}

.help-section ul,
.help-section ol {
  padding-left: 20px;
  line-height: 2;
  color: #555;
}

.help-section li {
  margin-bottom: 5px;
}

.help-table {
  width: 100%;
  border-collapse: collapse;
  margin: 15px 0;
  font-size: 14px;
}

.help-table th,
.help-table td {
  border: 1px solid #dcdfe6;
  padding: 10px;
  text-align: left;
}

.help-table th {
  background-color: #f5f7fa;
  font-weight: bold;
  color: #333;
}

.help-table td {
  color: #666;
}

.help-footer {
  text-align: center;
  padding: 20px 0;
  color: #666;
}
</style>
