"""
Prompt 模板管理器
负责管理预置 Prompt 模板，支持从数据库读取用户自定义模板
"""
import re
from jinja2 import Template as Jinja2Template
from app.core.edition import is_community_edition
from app.core.qa_judge_prompt_ce import (
    QA_JUDGE_DESCRIPTION_CE,
    QA_JUDGE_SYSTEM_PROMPT_CE,
    QA_JUDGE_USER_PROMPT_TEMPLATE_CE,
)
from app.models.ai import AiPromptTemplate


_prompt_initialized = False

EXTRA_INSTRUCTIONS_MAX_LEN = 2000


def append_extra_instructions(
    user_prompt: str,
    extra_instructions: str | None,
    *,
    scene: str = "functional",
) -> str:
    """将用户额外要求追加到 Prompt 末尾，优先级高于上文默认规则。"""
    extra = (extra_instructions or "").strip()[:EXTRA_INSTRUCTIONS_MAX_LEN]
    if not extra:
        return user_prompt
    if scene == "api_case":
        header = (
            "## 【用户额外要求 · 优先于上文通用规则】\n"
            "用户要求与上文冲突时，**以本节为准**（仍须遵守 JSON 数组结构与字段规范）：\n\n"
        )
    else:
        header = (
            "## 【用户额外要求 · 优先于上文通用规则】\n"
            "以下由平台自动处理，模型**禁止**输出或改写：title（完整标题）、所属产品、禅道模块、"
            "相关研发需求、适用阶段。\n"
            "用户要求与上文冲突时，**以本节为准**（仍须遵守 JSON 结构与上述禁止输出字段）：\n\n"
        )
    return user_prompt + "\n\n---\n" + header + extra


class PromptManager:
    """Prompt 模板管理器"""

    # 预置模板（系统默认）
    DEFAULT_TEMPLATES = {
        "api_case_generation": {
            "name": "API 测试用例生成",
            "scene_type": "api_case",
            "description": "基于接口定义生成 API 测试用例",
            "system_prompt": (
                "你是一位资深的 API 测试工程师，擅长设计边界值、异常场景、组合场景的测试用例。"
                "你必须严格输出标准 JSON 格式，不要包含 Markdown 代码块标记（如 ```json）。"
            ),
            "user_prompt_template": """请基于以下接口定义，生成 {{count}} 个高质量的 API 测试用例。

接口信息：
- 名称：{{api_name}}
- 方法：{{method}}
- 路径：{{path}}
- 描述：{{description}}
- 请求头：{{headers}}
- 请求参数：{{params}}
- 请求体：{{body}}
- 请求体类型：{{body_type}}
{% if body_fields %}
- 请求体字段（form-data）：{{body_fields}}
{% endif %}

{% if response_schema %}
响应结构定义：
{{response_schema}}
{% endif %}
{% if response_example %}
响应示例：
{{response_example}}
{% endif %}
{% if existing_cases %}
已有用例（共 {{existing_cases_count}} 条，展示最近 {{existing_cases_limit}} 条）：
{{existing_cases}}

重要：请勿生成与已有用例名称或场景高度重复的新用例；应补充尚未覆盖的边界/异常/鉴权场景。
可参考已有用例的断言风格与变量提取方式，但 expected 值需符合当前接口定义。
{% endif %}

要求：
1. **用例数量（硬性约束）**：必须且只能输出 **{{count}}** 条用例，JSON 数组长度必须等于 {{count}}，禁止超出。
{% if count == 1 %}
   - 仅 1 条时：只生成 1 条用例；场景以用户补充要求为准；若未指定则生成 1 条正向场景。
   - 禁止为覆盖多种场景而拆成多条。
{% else %}
   - 在 {{count}} 条以内合理分配，优先覆盖：正向、边界值、异常、鉴权（若需要 Token）等场景，不必每种都写满。
{% endif %}
2. 每个用例必须包含以下字段：
   - name：用例名称（中文，必须包含接口名称或功能主语，如"获取场景知识库列表-正向场景-合法参数"）
   - request_headers：请求头（覆盖或新增）；引用环境或上游变量时使用 ${{变量名}} 语法
   - request_params：查询参数（覆盖或新增，必须是数组，每个元素为 {name, value, type, required, description}）；value 中引用变量使用 ${{变量名}}
   - request_body_type：请求体类型，必须与接口一致（json / form-data / x-www-form-urlencoded / xml / raw）
   - request_body：请求体（覆盖或新增）。注意：当 request_body_type 为 form-data 时，request_body 必须是 {}，字段信息放在 request_body_fields 中
   - request_body_fields：form-data 字段数组（仅当 request_body_type 为 form-data 时必填），每个元素为 {name, value, field_type, file_name, mime_type, file_key, file_bucket, description}。field_type 可选 text 或 file；file 类型时 value 为空，file_key/file_bucket 由平台上传后填充，AI 生成用例时若无文件可留空并由用户上传
   - assertions：断言规则数组，每条包含 {type, target, operator, expected, description}
     * type: status_code / json_path / header / response_time / contains / not_contains
     * target: 当 type=json_path 时为 JSONPath 表达式（如 $.code）；type=header 时为头字段名；其他可为 null
     * operator: equals / not_equals / contains / not_contains / regex / gt / lt / gte / lte
     * expected: 期望值
     * description: 断言描述（可选）
     * 断言字段路径生成规则（非常重要）：
       - 如果提供了响应示例，必须严格基于响应示例中的实际字段路径生成断言
       - 响应示例中的字段名是什么，断言的 target 就必须是什么，严禁编造不存在的字段
       - 如果响应示例中没有 code 字段，就不要生成 $.code 的断言
       - 如果响应示例中 data 是数组（如 $.data[0].name），不要假设为对象（如 $.data.list）
       - 只能使用响应示例中明确存在的 JSONPath，禁止使用假设的字段名（如 $.data.projects）
       - 若响应示例为 SSE 文本（含 event:/data: 行），以各 data: 行内的 JSON 为准推断字段；流式片段可用 contains 断言匹配 data 内关键字段
     * 如果同时提供了响应结构定义（Schema）和响应示例，以响应示例为准生成断言路径
   - extractors：变量提取规则数组，每条包含 {name, source, path, description}
     * name: 变量名
     * source: json / header（json_path 请写 json）
     * path: 提取路径（JSONPath 或 header 字段名）
     * description: 描述（可选）
3. 输出格式：标准 JSON 数组，每个元素是一个用例对象。
4. 不要输出任何解释性文字，只输出 JSON。""",
            "examples": [],
        },
        "mock_data_generation": {
            "name": "Mock 响应体生成",
            "scene_type": "api_mock",
            "description": "根据接口描述 AI 生成 Mock 响应 JSON",
            "system_prompt": (
                "你是一位 API Mock 数据设计专家，擅长生成真实、结构合理的 JSON 响应。"
                "你必须严格输出标准 JSON 对象，不要包含 Markdown 代码块标记。"
            ),
            "user_prompt_template": """请为以下 Mock 接口生成合适的 HTTP 响应体 JSON。

接口信息：
- 名称：{{ name }}
- 方法：{{ method }}
- 路径：{{ path }}
- 期望状态码：{{ response_status }}
- 业务描述：{{ description }}

要求：
1. 输出一个 JSON 对象，必须包含字段：
   - response_body：Mock 响应体（object 或 array，符合 REST 常见结构，如 code/message/data）
   - response_status：HTTP 状态码整数（默认 {{ response_status }}）
2. response_body 字段名与类型应贴合路径与描述，数据应看起来真实（可虚构 id、时间戳等）
3. 只输出 JSON 对象，不要解释文字""",
            "examples": [],
        },
        "ui_case_generation": {
            "name": "UI 测试用例生成",
            "scene_type": "ui_case",
            "description": "基于自然语言描述和页面结构生成 UI 自动化测试步骤",
            "system_prompt": (
                "你是一位精通 Playwright 的 UI 自动化测试工程师。"
                "你的任务是将自然语言需求转换为平台标准的 UI 自动化测试步骤。"
                "你必须严格输出标准 JSON 格式，不要包含 Markdown 代码块标记。"
                "如果提供了页面元素列表，你必须从列表中选取定位器，严禁编造不存在的选择器。"
            ),
            "user_prompt_template": """请将以下测试需求转换为平台标准的 UI 自动化测试步骤。

需求描述：{{description}}
目标页面：{{page_url}}

{% if page_elements %}
页面可交互元素列表（请严格从以下元素中选择 locator，严禁编造）：
{{page_elements}}

定位器选择规则（按优先级，与录制引擎保持一致）：
1. 最优先使用元素列表中提供的 selector 字段（这是已经生成好的可用 CSS 选择器，严禁修改其中任何文本）
2. 使用 data-testid：[data-testid='xxx']
3. 使用 id 选择器：#元素id
4. 使用 get_by_text：get_by_text=可见文本（Playwright 原生文本定位，推荐用于按钮、链接、span 文本）
5. 使用 get_by_role：get_by_role=角色, 名称（如 get_by_role=button, 登录、get_by_role=link, 控制台）
6. 使用 name 属性选择器：tag[name='xxx']
7. 使用 aria-label 属性选择器：[aria-label='xxx']
8. 使用 title 属性选择器：tag[title='xxx']（常用于图标按钮、卡片等自定义组件）
9. 使用 class 选择器：.className（class 中有空格时取第一个，如 .btn-primary）
10. 兜底使用 CSS 选择器：tag:has-text("xxx")
11. 严禁编造不在上述列表中的选择器

【严格约束 - 违反会导致执行失败】
- 如果元素列表中某一行有 selector=xxx，你必须直接使用这个 xxx 作为 locator，严禁修改其中任何字符
- 严禁把 placeholder 文本从"密码"改成"请输入密码"，从"用户名"改成"请输入用户名"等
- 严禁给 selector 添加列表中不存在的属性或前缀
- 举例：如果列表中是 `selector=input[placeholder="密码"]`，你的 params.locator 必须是 `input[placeholder="密码"]`，不能是 `input[placeholder="请输入密码"]`
- 对于可见文本元素（如 `<span class="show-name">控制台</span>`），优先使用 `get_by_text=控制台`（Playwright 原生，最稳定）
- 对于有明确 role 的按钮/链接，使用 `get_by_role=button, 登录` 或 `get_by_role=link, 控制台`
- 如果元素有 data-testid 属性，必须优先使用 [data-testid='xxx']
{% endif %}

{% if executed_steps %}
【已执行步骤上下文】
以下步骤已经在浏览器中执行完毕，页面状态已发生变化：
{{executed_steps}}

当前页面 URL：{{current_url}}
当前轮次：第 {{round_index}} 轮

重要规则：
- 请只生成**剩余未执行**的步骤，严禁重复已执行步骤
- 如果页面已跳转到新 URL，请基于当前页面的 DOM 生成新步骤
- 如果所有操作都已完成，请返回空数组 []
{% endif %}

步骤格式要求（JSON 数组，每个元素）：
- keyword: 中文动作名称
- method: 英文方法名（必须严格匹配下方列表）
- desc: 步骤中文描述
- params: 参数对象（参数名必须严格匹配）
- children: 子步骤数组（通常为 []）

【页面操作】
- open_url: {url, wait_until:"load", timeout:30000}
- refresh: {wait_until:"domcontentloaded", timeout:30000}
- go_back: {timeout:30000, fallback_url:""}
- scroll_to_height: {height}
- execute_script: {script, args:[]}
- save_page_img: {name}
- open_new_page: {tag:""}
- switch_to_page: {tag, index, title, url}
- close_page: {tag, index, title, url}
- reset_browser_context: {}
- close: {}

【元素操作】
- fill_value: {locator, value, timeout:20000}
- click_ele: {locator, index:1, force:false, timeout:20000}
- double_click_ele: {locator, index:1, force:false, timeout:20000}
- clear_value: {locator, timeout:20000}
- set_checked: {locator, timeout:20000}
- hover: {locator, timeout:20000}
- focus_element: {locator, timeout:20000}
- select_option: {locator, value, timeout:20000}
- type_value: {locator, value, timeout:20000}
- drag_and_drop: {start_selector, end_selector, timeout:20000}
- long_click_element: {locator, delay:0.1}
- upload_file: {locator, file_path, timeout:20000}

【鼠标键盘】
- mouse_click: {x, y, button:"left", count:1}
- move_mouse: {x, y}
- mouse_down: {button:"left"}
- mouse_up: {button:"left"}
- mouse_wheel: {x, y}
- press_key: {key}
- press_type: {keys}

【iframe操作】（如果操作在 iframe 内时使用）
- frame_fill_value: {frame, locator, value, timeout:20000}
- frame_click_element: {frame, locator, index:1, button:"left", force:false, timeout:20000}
- frame_hover: {frame, locator, timeout:20000}
- frame_focus_element: {frame, locator, timeout:20000}
- frame_select_option: {frame, locator, value, timeout:20000}
- frame_type_value: {frame, locator, value, timeout:20000}
- frame_long_click_element: {frame, locator, delay:0.1}
- frame_drag_and_drop: {frame, start_selector, end_selector, timeout:20000}

【等待操作】
- set_default_timeout: {timeout:20000}
- wait_for_time: {timeout:2000}
- wait_for_load: {}
- wait_for_network: {}
- wait_for_element: {locator, timeout:20000}

【断言操作】
- kw_assert_page_title: {title}
- kw_assert_page_url: {url}
- kw_assert_value: {locator, value}
- kw_assert_element_text: {locator, text, match_mode:"exact"|"contains"}
- kw_assert_element_text_contains: {locator, text}
- kw_assert_text_contains: {text}
- kw_assert_attribute: {locator, attr_name, value}
- kw_assert_visible: {locator, index:1}
- kw_assert_hidden: {locator, index:1}
- kw_assert_enabled: {locator, index:1}
- kw_assert_disabled: {locator, index:1}
- kw_assert_checked: {locator, index:1}
- kw_assert_empty: {locator, index:1}
- kw_assert_editable: {locator, index:1}
- kw_assert_focused: {locator, index:1}

【变量提取】
- extract_text: {locator, var_name, index:1, timeout:20000}
- extract_attribute: {locator, attr_name, var_name, index:1, timeout:20000}
- extract_page_url: {var_name}

【条件分支】
- condition_branch: {branches:[{name, condition:{type, locator, expected_value}, steps:[]}]}

生成规则：
1. 每个页面操作后建议加 wait_for_time 或 wait_for_element 确保稳定
2. **点击触发弹窗/浮层后**，必须加 wait_for_element 等待弹窗内稳定元素（如 get_by_role=dialog 或弹窗容器），再在弹窗内 click/fill
3. 弹窗内元素 locator 优先使用 `弹窗容器 >> get_by_text=`，避免裸 get_by_text 全页匹配
4. 优先使用稳定选择器：#id > [name='xxx'] > [aria-label='xxx'] > .class
5. 避免使用动态 class（含 random/hash 的 class）
6. 输入操作使用 fill_value；需要模拟真实键盘输入用 type_value
7. 引用环境变量或动态值时，params 中的字符串统一使用 ${{变量名}}，如 ${{username}}、${{password}}、auto_${{random_int}}
8. 如果需求没提到关闭浏览器，最后一步不加 close
9. 严禁输出列表中不存在的 method 或参数名
10. 输出必须是可直接解析的 JSON 数组，不要任何解释文字""",
            "examples": [],
        },
        "ui_agent_plan": {
            "name": "UI Agent 单步规划",
            "scene_type": "ui_case",
            "description": "基于无障碍树 snapshot 规划下一步 UI 操作（MCP 思路）",
            "system_prompt": (
                "你是一位 UI 自动化 Agent。根据页面无障碍树 snapshot 和用户目标，"
                "每次只规划**下一步**操作。你必须严格输出 JSON 对象，不要 Markdown 代码块。"
                "定位器必须来自 snapshot 中当前可见、可交互的元素，严禁编造或对 hidden 元素做 wait。"
                "定位优先级与录制器一致：data-testid > #id > get_by_role > name/label/placeholder > get_by_text（末选）。"
            ),
            "user_prompt_template": """用户目标：{{description}}
当前页面 URL：{{current_url}}
当前是第 {{step_index}} 步规划
Snapshot 类型：{{snapshot_type}}

{% if has_stuck_hint %}
【本轮必读】{{stuck_hint}}
{% endif %}

{% if executed_steps %}
已执行步骤（JSON）：
{{executed_steps}}
{% endif %}

页面无障碍树 / 元素 snapshot：
{{accessibility_snapshot}}

请输出单个 JSON 对象（不是数组）：
{
  "done": false,
  "message": "若 done=true 时说明完成原因",
  "step": {
    "keyword": "中文动作名",
    "method": "英文方法名",
    "desc": "步骤描述",
    "params": {},
    "children": []
  }
}

规则：
1. 若目标已全部完成，设 done=true，step 可省略
2. 若还需操作，设 done=false，step 仅包含**一步**
3. method 仅限：open_url, fill_value, click_ele, hover, select_option, type_value, clear_value,
   wait_for_time, wait_for_element, wait_for_load, press_key, scroll_to_height
4. params.locator 必须是**字符串**（禁止 JSON 对象）。**点击按钮/链接**时按优先级选用（snapshot 里有什么用什么）：
   - 有 id → `#btn-login` 或 `//button[@id='btn-login']`
   - 有 data-testid → `[data-testid=xxx]`
   - 否则 → `get_by_role=button, <按钮完整可见名称>`（名称与 snapshot 一致，含空格）
   - **仅当**无 id/role 且文本唯一时，才用 `get_by_text=`；禁止用「登录」「提交」等短词（易误点说明文字）
5. **输入框**：`#id` > `get_by_label=` > `get_by_placeholder=`；禁止对 placeholder 用 get_by_text=
6. **优先 click_ele / hover 完成导航**；同一按钮已成功点击且 snapshot 已换屏后，不得再次 click 同一 locator
7. **禁止**与已执行步骤相同的 method+locator；若结构未变说明点错，必须换 #id 或 get_by_role
8. **禁止**滥用 wait_for_element 等待 hidden 节点；应直接 click 可见父级
9. 用户描述「点击 XX 按钮」时，locator 必须对应 snapshot 里该 button 的 id 或 role+name，不要编造
10. 只输出 JSON 对象""",
            "examples": [],
        },
        "ui_locator_heal": {
            "name": "UI 定位器自愈",
            "scene_type": "ui_case",
            "description": "步骤执行失败时基于 snapshot 推荐新 locator",
            "system_prompt": (
                "你是 Playwright 定位专家。根据页面 snapshot 和失败信息，"
                "推荐一个更可能成功的 locator。严格输出 JSON，不要 Markdown。"
            ),
            "user_prompt_template": """步骤方法：{{method}}
失败定位器：{{failed_locator}}
步骤描述：{{step_desc}}
错误信息：{{error_message}}
页面 URL：{{page_url}}
Snapshot 类型：{{snapshot_type}}

页面 snapshot：
{{accessibility_snapshot}}

输出 JSON：
{
  "locator": "新定位器",
  "confidence": "high|medium|low",
  "reason": "简要说明"
}

定位器规则（与平台一致，必须是字符串，禁止 Playwright 函数写法）：
- 正确：get_by_placeholder=密码、get_by_role=row, 0302、#loginBtn
- 错误：get_by_placeholder("密码")、page.get_by_role(...)、get_by_role='row'（role/name 禁止加引号）、row=0302（必须用 get_by_role=row, 0302）
- 优先 data-testid、#id、name、get_by_role=、get_by_placeholder=、get_by_label=
- get_by_text= 对 input placeholder 无效；失败定位器为「请输入…」或短 placeholder 文案时改用 get_by_placeholder=
- 严禁返回与失败定位器完全相同的字符串
- **错误含 element is not visible 时**：禁止继续用 (//xpath)[1] 等纯序号定位；改用可见结构特征（如含操作按钮的行、唯一 id、title 等）
- **步骤描述 step_desc 是业务意图**：新定位器必须能完成 step_desc 描述的操作（如「点击基础设置」必须点到「基础设置」，不能改成「设置」）
- 页面上有多个相似文案时，选与 step_desc **完全匹配** 或 **更长更具体** 的那个，禁止用更短子串替代（例：失败 get_by_text=基础设置 时禁止改成 get_by_text=设置）
- 常见短词（设置、登录、确定等）易重复，优先用带区域/结构信息的定位（侧栏菜单、顶栏导航、父级 class 等），必要时配合 index
- **弹窗/浮层内元素**：优先 `弹窗容器 >> get_by_text=` 或 `get_by_role=dialog >> ...`；禁止裸 `get_by_text` 全页搜索
- **文本含 $ 或反斜杠时禁止** `tag:has-text("...")`（Playwright CSS 会报 BADSTRING），必须用 `get_by_text=` 或 `父级 >> get_by_text=`
- 只输出 JSON 对象""",
            "examples": [],
        },
        "requirement_parse": {
            "name": "需求文档解析",
            "scene_type": "requirement_parse",
            "description": "从产品需求文档中提取结构化功能点",
            "system_prompt": (
                "你是一位资深的需求分析师和测试专家。"
                "你的任务是从产品需求文档中提取结构化的功能点，每个功能点应包含验收标准。"
                "你必须严格输出标准 JSON 格式，不要包含 Markdown 代码块标记。"
            ),
            "user_prompt_template": """请解析以下产品需求文档，提取所有功能点：

需求文档内容：
{{requirement_content}}

输出要求：
1. 提取每个独立的功能点
2. 每个功能点包含：
   - id: 功能点编号（如 f-001）
   - title: 功能点标题（中文，简明扼要）
   - description: 功能描述
   - acceptance_criteria: 验收标准数组（每条标准必须可验证）
   - priority: 优先级（high/medium/low）
   - page_module: 所属页面/模块
3. 输出 summary: 文档总体概述（功能点总数、核心业务）
4. 输出标准 JSON 格式：
{
  "summary": "...",
  "features": [
    {
      "id": "f-001",
      "title": "...",
      "description": "...",
      "acceptance_criteria": ["...", "..."],
      "priority": "high",
      "page_module": "登录模块"
    }
  ]
}
5. 不要输出任何解释性文字，只输出 JSON。""",
            "examples": [],
        },
        "requirement_case_generation": {
            "name": "基于功能点生成测试用例",
            "scene_type": "requirement_case",
            "description": "基于需求功能点生成功能测试用例",
            "system_prompt": (
                "你是一位资深的功能测试工程师。基于给定的功能点，设计覆盖全面的功能测试用例。"
                "你必须严格输出标准 JSON 格式，不要包含 Markdown 代码块标记。"
            ),
            "user_prompt_template": """请基于以下功能点，生成 {{case_type}} 测试用例。

功能点信息：
- 标题：{{feature_title}}
- 描述：{{feature_description}}
- 验收标准：{{acceptance_criteria}}
- 优先级：{{priority}}
- 所属模块：{{page_module}}

生成要求：
1. 覆盖以下测试类型：
   - 正向流程（正常操作路径）
   - 反向流程（异常/错误操作路径）
   - 边界值（最大值、最小值、空值、超长输入）
   - 等价类划分（有效/无效等价类各至少一个）
   - 状态转换（若涉及状态变化）
   - 权限控制（若涉及不同角色）
2. 每个用例包含：
   - name: 用例名称
   - pre_condition: 前置条件
   - steps: 测试步骤（数组，每步包含 action 和 expected）
   - priority: 用例优先级（P0/P1/P2/P3）
   - tags: 标签数组
3. 用例总数控制在 {{count}} 条以内，优先保证核心路径覆盖
4. 输出标准 JSON 数组
5. 不要输出任何解释性文字，只输出 JSON。""",
            "examples": [],
        },
        "requirement_doc_understand": {
            "name": "需求文档图片理解",
            "scene_type": "requirement_parse",
            "description": "Vision 模型理解需求文档中的单张图片",
            "system_prompt": (
                "你是一位资深需求分析师与功能测试专家，擅长从原型图、流程图、界面截图中提取可测试信息。"
                "输出须客观、可验证，优先引用图中可见的文字与控件，不要臆造需求中未出现的内容。"
                "严格输出 JSON，不要 Markdown 代码块或解释文字。"
            ),
            "user_prompt_template": """以下是需求文档的文字摘要（供上下文参考，可与图片交叉印证）：
{{doc_text_excerpt}}

请分析**当前这张图片**，提取与功能测试直接相关的信息。要求：
1. **ui_elements**：列出可见控件/区域（按钮、输入框、Tab、表格列、状态标签等），尽量使用图中或上下文中出现的**原文名称**
2. **exact_messages**：列出图中或需求可见的**固定文案**（按钮文字、提示语、错误提示、字段标签、单位如 MB/个/字等），逐条原文摘录
3. **business_rules**：从图中或上下文可推断的**业务规则与边界**（必填、禁用条件、数量/大小上限、状态流转等）；无依据则不写
4. **test_points**：针对本图应设计的测试关注点（含 UI 布局/可见性/交互反馈）
5. **module** / **summary**：模块名与一句话概述

输出 JSON（字段不可省略，无内容时用空数组 []）：
{
  "module": "模块名",
  "summary": "图片内容概述",
  "ui_elements": ["左侧「抽取配置区」", "按钮「开始抽取」", "..."],
  "exact_messages": ["上传文件不超过50M", "请检查配置是否正确", "..."],
  "business_rules": ["未上传文件时抽取按钮禁用", "..."],
  "test_points": ["验证无文件时抽取按钮灰显不可点", "..."]
}
只输出 JSON，不要其他文字。""",
            "examples": [],
        },
        "requirement_doc_to_cases": {
            "name": "需求文档生成功能测试用例",
            "scene_type": "requirement_case",
            "description": "基于需求文档摘要生成功能测试用例（禅道格式）",
            "system_prompt": (
                "你是一位有 10 年经验的功能测试工程师，编写可直接执行的手工测试用例。"
                "所有步骤、预期、数值、提示文案须**有据可依**：只能来自下方【本次生成范围】正文、"
                "其中 [图-N] 读图摘要，或需求中明确写明的测试环境地址；禁止编造需求未出现的上限、错误码或按钮文案。"
                "高质量标准：前置条件可落地、每步操作含对象+动作+关键数据、预期可观察可判定；"
                "涉及表单/反馈/弹窗/跳转/多状态切换的流程须拆成多步，禁止为凑条数写一步式浅用例。"
                "你必须严格输出标准 JSON 数组，不要 Markdown 代码块。"
                "每个用例 steps 数组每一项须同时含 step 与 expect，一步一预期，禁止合并多步。"
            ),
            "user_prompt_template": """请基于以下需求文档信息，生成约 {{count}} 条功能测试用例（参考目标，可略多或略少，以**覆盖要点与质量**为准，不必凑满条数）。

需求名称：{{requirement_name}}

{{naming_rules}}

{{count_quality_hint}}

【本次生成范围 · 章节】
{{scope_section_titles}}

【本次生成范围 · 正文与读图已按章节顺序合并】
{{scoped_content}}

（若上方为空可参考：{{doc_text}}）

---

## 测试设计维度配比（写入 test_design，**不要**写入 type）
- **正向流程**（主路径成功）：约 35%～45%
- **异常/反向**（非法输入、权限不足、配置缺失、操作不允许）：约 30%～40%
- **边界值**（上限/下限/空值/超长/临界个数/静默逻辑）：约 15%～25%
- 若范围内出现 **API 调用、接口、OpenAPI** 等：test_design 用「接口校验」，type 用「接口测试」
- test_design 仅允许：正向流程|异常/反向|边界值|接口校验|其他

## 前置条件 precondition（每条必填，建议三段式，换行分隔）
1. **环境**：测试站点/入口 URL（需求中出现的须写完整；无则写「测试环境已部署可访问」）
2. **角色/权限**：登录账号类型或权限状态（如「已登录且具备文档抽取权限」）
3. **数据/状态**：已上传的文件、已选场景、已配字段、特定评分/记录等与本用例相关的准备项（**须写具体数值或状态**）

## 步骤 step 与预期 expect（专业写法 · 质量重点）
- **step** 须含：**操作对象 + 具体动作 + 关键输入数据**（按钮/菜单/Tab 等 UI 名称用英文双引号包裹，如 点击"提交反馈"按钮；**禁止**使用「」书名号）
- **expect** 须**可观察、可判定**：界面文案/Toast/字段值/控件显隐/列表条数/按钮禁用态/跳转页面/是否入库等；**每一步 expect 只描述该步操作后的直接结果**
- **步数策略**：
  - **只读/静默/单点展示**（如仅查看卡片数值、标签文案、某分数下控件不出现）：**1 步**即可，但 expect 须具体到控件与文案
  - **交互流程**（选择类型、填写反馈、提交、切换 Tab、刷新、二次确认）：通常 **2～4 步**（如：进入页面→执行操作→确认界面反馈/副作用）
- steps 为 JSON 数组，**每一步一个对象**，每项同时含 step 与 expect
- **禁止**为凑步数重复相同 expect；**禁止**只在 expect 里用「1.xxx\\n2.yyy」编号而 step 只有一条
- **禁止**将「1.xxx\\n2.yyy」写在同一个 step 或 expect 字符串内

## 需求 grounding（硬性）
- 文件大小、数量上限、字数限制、配额、评分阈值、错误提示等**必须与上文一致**；上文未写明的写「（需求待确认）」勿虚构具体数字
- 范围内含 **[图-N]** 或读图 JSON 摘要时：相关用例至少 **30%** 应引用具体 **ui_elements / exact_messages**（控件名、布局、提示原文）

## 禁止使用的空洞表述（step/expect/precondition 均禁止）
「执行操作」「符合预期」「显示正常」「功能正常」「操作成功」「执行步骤 N」等无具体对象的描述

---

## 输出 JSON 字段（每个用例一个对象；不要产品/禅道模块/研发需求/适用阶段，由平台配置）
- main_module, sub_module, feature_point（同批勿重复）, case_description, module
- precondition, steps: [{ "step": "...", "expect": "..." }, ...]
- priority: 仅 "1"(高)/"2"(中)/"3"(低)/"4"(建议)
- test_design: 正向流程|异常/反向|边界值|接口校验|其他（必填，表示本条用例的测试设计维度）
- type: 禅道「用例类型」，仅允许：场景测试|功能测试|性能测试|配置相关|安装部署|安全相关|接口测试|其他|自动化测试；**默认「功能测试」**（勿把正向/异常/边界写入 type）

**禁止**输出 title 字段；**禁止**自行拼接【#...】完整标题。
只输出 JSON 数组，不要任何解释文字。""",
            "examples": [],
        },
        "requirement_doc_to_test_points": {
            "name": "需求文档生成测试点",
            "scene_type": "test_analysis",
            "description": "基于需求文档章节内容生成结构化测试点（思维导图节点）",
            "system_prompt": (
                "你是一位资深测试分析师。你的任务是从产品需求文档中提取可验证的测试点，"
                "用于后续编写测试方案与测试用例。测试点描述验证意图，不要写详细操作步骤。"
                "你必须严格输出标准 JSON 数组，不要包含 Markdown 代码块标记。"
            ),
            "user_prompt_template": """请基于以下需求文档内容，生成约 {{count}} 条测试点（参考目标，可略多或略少，以覆盖要点为准）。

需求名称：{{requirement_name}}

【本次分析范围 · 仅限以下章节（勿涉及范围外功能）】
{{scope_section_titles}}

【本次分析范围 · 正文与读图已按章节顺序合并】
{{scoped_content}}

---

## 测试点要求
1. 每条测试点是一个**可验证的关注点**，不是完整用例步骤
2. **仅**针对上方列出的章节范围内的功能设计测试点，禁止写未选章节的内容
3. 覆盖类型：正向、异常、边界、权限、状态、兼容、API 等
4. **section_title**：必填，须与上方章节列表中的标题**完全一致**（测试点归属的最具体章节）
5. **main_module / sub_module**：与 section_title 对应层级一致（一级/二级章节标题）
6. module_path 格式：「主模块/子模块」
7. 标题简明（≤50字），description 说明验证什么、依据什么
8. acceptance_ref 摘录需求原文或读图摘要中的依据（可选）
9. 同批测试点 title 勿重复

## 输出 JSON 字段（每个测试点一个对象）
- title: 测试点标题
- section_title: 归属章节标题（须来自上方章节列表）
- description: 验证说明（1～3 句）
- test_type: 正向|异常|边界|权限|状态|兼容|性能|API|其他
- priority: P0|P1|P2|P3
- main_module, sub_module, module_path
- acceptance_ref: 需求依据摘录（可选）
- feature_point: 功能点名称（可选）

**禁止**输出 steps、用例步骤、完整测试用例。
只输出 JSON 数组，不要任何解释文字。""",
            "examples": [],
        },
        "requirement_test_points_to_scheme": {
            "name": "测试点生成测试方案",
            "scene_type": "test_analysis",
            "description": "基于测试点与需求正文生成结构化测试方案",
            "system_prompt": (
                "你是一位有企业级项目经验的测试经理，编写可落地的《测试方案》。"
                "环境、账号、地址、版本等信息必须优先来自【需求正文摘录】或【测试环境补充】；"
                "需求未写明的项填「待确认」并简要说明需向谁确认，禁止编造具体 URL、IP、账号密码。"
                "严格输出 JSON 对象，不要 Markdown 代码块。"
            ),
            "user_prompt_template": """请为以下需求编写测试方案。

需求名称：{{requirement_name}}
方案标题：{{scheme_title}}

【本次方案覆盖章节】
{{scope_section_titles}}

【需求正文摘录 · 环境与业务事实须以此为准】
{{requirement_excerpt}}

【测试环境补充 · 测试负责人填写，可与需求合并；未填则勿编造】
{{environment_hints}}

【测试点清单 · 共 {{test_point_count}} 条】
{{test_points}}

---

## 写作要求
1. **测试范围**：in_scope 须对应上方章节/测试点模块；out_of_scope 写 2～5 条明确不测项
2. **测试策略**：types 含功能/界面/异常/边界等（与测试点类型分布一致）；smoke 以 P0 测试点为主
3. **测试环境**（重点）：
   - 从需求摘录中提取：系统名称、访问地址/入口、部署环境、浏览器/客户端、账号角色、依赖服务
   - 无依据的字段写「待确认：…」
   - 不要写「测试环境已部署可访问」等空话
4. **通过准则**：结合 P0/P1 数量给出可量化标准（如 P0 100% 通过）
5. **风险**：至少 2 条，与需求或测试点相关

## 输出 JSON 结构（字段不可省略，无内容用「待确认」或空数组）
{
  "scope": {
    "in_scope": ["..."],
    "out_of_scope": ["..."]
  },
  "strategy": {
    "types": ["功能测试", "界面测试"],
    "smoke_criteria": "冒烟：全部 P0 测试点通过",
    "regression_scope": "回归：本次 in_scope 全部测试点",
    "approach": "黑盒功能测试为主；按模块执行测试点"
  },
  "environment": {
    "system_name": "被测系统名称（来自需求）",
    "test_env": "环境名称，如 SIT/UAT/预发",
    "access_entry": "访问入口 URL 或路径（无则待确认）",
    "deploy_version": "版本/构建号（无则待确认）",
    "client_requirements": ["浏览器 Chrome 最新版", "分辨率 1920×1080"],
    "accounts_roles": ["角色A：用途", "角色B：用途"],
    "test_data": "测试数据准备说明（文件样例、库表、配置项）",
    "dependencies": ["依赖服务/中间件，如 MinIO、LLM API"],
    "tools": ["禅道", "抓包工具等"]
  },
  "exit_criteria": {
    "pass_rate": "P0 100%；P1≥95%",
    "blockers": ["无 P0 遗留缺陷", "..."],
    "deliverables": ["测试方案", "测试点执行记录", "缺陷清单"]
  },
  "risks": [
    {"item": "风险", "mitigation": "应对"}
  ],
  "test_point_summary": [
    {"module": "模块路径", "count": 5, "point_ids": [1, 2, 3]}
  ]
}

test_point_summary 的 point_ids 必须引用上方测试点 id。只输出 JSON。""",
            "examples": [],
        },
        "requirement_test_points_to_cases": {
            "name": "测试点生成功能测试用例",
            "scene_type": "test_analysis",
            "description": "基于已确认测试点展开为可执行的手工功能用例（禅道格式槽位）",
            "system_prompt": (
                "你是一位有 10 年经验的功能测试工程师。用户已完成测试分析并产出测试点清单，"
                "你的任务是将测试点展开为**可执行**的手工功能测试用例（含具体步骤与可验证预期）。"
                "步骤与数据须优先来自【需求摘录】与【测试点说明】；无依据时写「（待确认）」勿编造 URL、错误码。"
                "每条用例须能追溯到至少一个测试点 id（见输出要求）。"
                "严格输出 JSON 数组，不要 Markdown 代码块；每个用例 steps 每项须同时含 step 与 expect。"
            ),
            "user_prompt_template": """请基于以下测试点，生成约 {{count}} 条功能测试用例（参考目标，以**覆盖所列测试点**为主，可一条测试点对应一条或多条用例）。

需求名称：{{requirement_name}}
用例批次：{{case_batch_name}}

{{naming_rules}}

【需求正文摘录 · 步骤与预期的事实依据（可选）】
{{requirement_excerpt}}

【测试点清单 · 共 {{test_point_count}} 条，须全部覆盖】
{{test_points}}

---

## 生成规则
1. **覆盖**：上方每个测试点 id 至少出现在一条用例的 `source_test_point_ids` 中
2. **类型**：按测试点 test_type 展开（正向→主路径；异常/边界/权限→对应用例）
3. **步骤**：steps 为数组，每项须同时含 step 与 expect；只读/静默校验 1 步即可，表单/反馈/提交等交互流程通常 2～4 步；禁止一步式浅用例与重复 expect
4. **优先级**：测试点 P0→用例 priority "1"；P1→"2"；P2→"3"；P3→"4"
5. **禁止**空洞表述：「符合预期」「功能正常」「操作成功」等

## 输出 JSON（每对象一条用例；不要 title 字段，不要产品/禅道模块/研发需求）
- main_module, sub_module, feature_point, case_description, module
- precondition（环境/角色/数据三段式，换行分隔）
- steps: [{ "step": "...", "expect": "..." }, ...]
- priority: "1"|"2"|"3"|"4"
- test_design: 正向流程|异常/反向|边界值|接口校验|其他
- type: 禅道用例类型，默认「功能测试」（勿写正向/异常/边界）
- source_test_point_ids: [测试点 id 数字数组]
- keywords: 可选，建议含 `tp:#id` 便于追溯

只输出 JSON 数组，不要解释文字。""",
            "examples": [],
        },
        "requirement_doc_supplement_cases": {
            "name": "需求文档补充功能测试用例",
            "scene_type": "requirement_case",
            "description": "在已有批次用例基础上追加新用例，避免重复",
            "system_prompt": (
                "你是一位有 10 年经验的功能测试工程师。"
                "用户已对某一批次生成过测试用例，现需在相同需求范围内补充遗漏场景。"
                "补充用例须与【已有用例】在验证点上明显区分，且同样满足：步骤可执行、预期可验证、"
                "数值与文案有据可依（来自需求正文或读图摘要）。"
                "严格输出 JSON 数组，不要 Markdown 代码块。"
            ),
            "user_prompt_template": """请基于以下需求信息，为批次「{{batch_name}}」**补充**约 {{count}} 条功能测试用例。

需求名称：{{requirement_name}}

{{naming_rules}}

【本批次已生成用例 · 共 {{existing_count}} 条，请勿重复】
{{existing_cases}}

【已有功能点名称 · 禁止重复】
{{existing_feature_points}}

【本次补充所依据的需求范围 · 正文与读图已合并】
{{scoped_content}}

---

## 补充策略（优先补已有用例未覆盖的 test_design）
- **边界/异常/权限/状态/API 参数** 等遗漏场景
- test_design 配比参考：正向约 35%、异常约 35%、边界约 25%（在不与已有用例重复的前提下）
- 若已有用例步骤偏泛，补充的用例须更具体（含操作对象、输入数据、可观察预期）

## 写法要求（与正式生成一致）
- **precondition**：环境 + 角色/权限 + 数据/状态（三段式，数据须具体）
- **steps**：每项含 step 与 expect；只读校验 1 步即可，交互流程 2～4 步；UI 名称用英文双引号；expect 须具体可判定
- **grounding**：限额、错误提示、评分阈值等须来自上文；无依据写「（需求待确认）」
- 含 [图-N] 或读图摘要时，补充用例应优先覆盖图中 **ui_elements / exact_messages** 相关场景

## 输出字段
main_module, sub_module, feature_point（须区分已有）, case_description, module,
precondition, steps[{step,expect}]（步数不限）, priority(1-4),
test_design（正向流程|异常/反向|边界值|接口校验|其他）,
type（禅道用例类型，默认「功能测试」，勿写正向/异常/边界）

**禁止**输出 title；**禁止**自行拼接完整标题。
只输出**新增**用例的 JSON 数组，条数为参考目标，可略多略少。""",
            "examples": [],
        },
        "failure_analysis": {
            "name": "失败原因分析",
            "scene_type": "failure_analysis",
            "description": "分析测试执行失败的原因并给出修复建议",
            "system_prompt": (
                "你是一位测试分析师，擅长从请求/响应/日志/UI 截图中定位问题根因。"
                "若用户消息附带失败步骤截图，请结合页面元素、错误提示、弹窗、空白页等视觉信息综合判断。"
                "请用中文回答，结构化输出。"
            ),
            "user_prompt_template": """请分析以下测试执行失败的原因：

执行类型：{{target_type}}
{% if target_type == "api" %}
请求方法：{{request_method}}
请求URL：{{request_url}}
请求头：{{request_headers}}
请求体：{{request_body}}
响应状态码：{{response_status}}
响应体：{{response_body}}
{% endif %}
{% if target_type == "ui" %}
执行步骤：{{steps}}
失败步骤索引：{{failed_step_index}}
错误截图描述：{{screenshot_desc}}
{% endif %}

错误信息：{{error_msg}}
执行日志：{{logs}}

请输出 JSON 格式：
{
  "root_cause": "核心根因（1句话总结）",
  "possible_causes": ["可能原因1", "可能原因2"],
  "suggestions": ["修复建议1", "修复建议2"],
  "confidence": 0.85,
  "category": "配置错误|环境问题|代码缺陷|数据问题|网络问题|断言错误"
}
不要输出任何解释性文字，只输出 JSON。""",
            "examples": [],
        },
        "report_summary": {
            "name": "测试报告摘要",
            "scene_type": "report_summary",
            "description": "基于执行记录生成测试报告文字摘要",
            "system_prompt": (
                "你是一位测试经理，擅长从测试数据中提炼关键结论。"
                "请用中文生成简洁、专业的测试报告摘要。"
            ),
            "user_prompt_template": """请基于以下测试执行数据，生成测试报告摘要。

执行数据：
{{execution_data}}

要求：
1. 总结本次测试的整体情况（通过率、主要问题）
2. 对 failed_case_samples / failed_suite_samples 中的失败用例，**务必引用 error_hint、failed_step_keyword、log_error_excerpt 中的具体信息**；若某条 data_complete=false 且上述字段均为空，才说明「该用例缺少详细错误日志」
3. 列出 Top 3 需要关注的问题（尽量具体到用例名与失败步骤/错误信息）
4. 给出可执行的下一步建议（如查看失败步骤截图、重新运行单用例、检查环境变量等）
5. 字数控制在 300 字以内
6. 输出 JSON 格式：
{
  "summary": "总体概述",
  "highlights": ["要点1", "要点2", "要点3"],
  "recommendations": ["建议1", "建议2"]
}
不要输出任何解释性文字，只输出 JSON。""",
            "examples": [],
        },
        "ui_record_optimize": {
            "name": "录制步骤 AI 优化",
            "scene_type": "ui_case",
            "description": "基于用户录制操作，AI 删除多余步骤并优化描述为自然语言",
            "system_prompt": (
                "你是一个专业的 UI 自动化测试用例优化专家。"
                "你的任务是对机器录制的测试步骤进行精简和描述优化。"
                "【核心要求】你必须真正执行删减，不能原样返回所有步骤。"
                "优化后的步骤数量必须明显少于原始步骤，否则就是失败。"
                "你必须严格输出标准 JSON 格式，不要包含 Markdown 代码块标记（如 ```json），直接输出纯 JSON 文本。"
            ),
            "user_prompt_template": """测试目的：{{description}}

原始步骤（共 {{steps_count}} 步）：
{{steps_text}}

========== 重要背景（必须了解） ==========
1. 本系统使用 Playwright 自动化框架，click_ele、fill_value、open_url 等操作本身带有自动等待机制，不需要大量显式 wait_for_time。
2. 录制产生的 wait_for_time 大部分确实是用户自然停顿，但以下场景的等待是有意义的，不可删除：
   - open_url（页面跳转）后的 wait_for_time：新页面需要加载时间，Angular/Vue 组件渲染需要时间
   - hover（鼠标悬停）后的 wait_for_time：悬浮菜单/按钮的显示动画需要时间
   - 下拉框加载、弹窗动画、Ajax 加载后首次操作：需要等待元素出现
3. 页面自动重定向（如打开首页后自动跳到登录页，或登录成功后自动跳回首页）产生的 open_url 也是多余的，只保留用户首次手动访问的 open_url 即可。

========== 优化任务（必须执行，不能跳过） ==========

【任务1：必须删除以下类型步骤】
- 重复导航：只保留第一个 open_url，后续所有 open_url（包括重定向产生的）全部删除
- 冗余等待（wait_for_time）的删除规则：
  ★ 以下等待【严禁删除】，删除会导致执行失败：
    - open_url 后的 wait_for_time（新页面加载、Angular/Vue 组件渲染需要时间）
    - hover 后的 wait_for_time（悬浮菜单/按钮的显示动画需要时间）
    - 下拉框加载、弹窗动画、Ajax 加载后首次操作的 wait_for_time
  ★ 以下等待【必须删除】：
    - 用户自然停顿产生的长时间等待（如思考、查找元素时的停顿，通常 >5秒）
    - 两个连续操作之间无明显状态变化的 wait_for_time
- 冗余点击：点击空白处、点击已聚焦的输入框、点击已经选中的下拉框等无意义点击全部删除
- 重复操作：同一元素的连续多次无意义点击只保留一次
- hover（鼠标悬停）精简规则（必须根据用户描述判断，不能一刀切保留所有 hover）：
  - 用户描述中明确提到的 hover 场景（如"鼠标悬浮一个知识库，等出现编辑按钮"）必须保留
  - hover 到页面布局容器（如 nz-content、body、背景 div、弹窗容器）的步骤一律删除
  - hover 后没有后续 click 依赖的（如 hover 到空白区域、内容容器后没有任何 click），可以删除
  - hover 后立刻 click 同一元素的，该 hover 可以删除（click 本身会触发 hover）
  - 只有 hover 到 A 元素后，需要去点击 B 元素（如 hover 显示菜单后点击菜单项），这种 hover 才需要保留
  - 特别注意：如果用户描述中没有提到某个 hover 的目的，且该 hover 的元素不是明显的可交互组件，优先考虑删除

【任务2：必须合并以下连续步骤】
- 先点击输入框 → 再输入内容 → 合并为1个 fill_value 步骤，desc="在 xxx 输入框输入 yyy"
- 先点击下拉框 → 再选择选项 → 合并为1个步骤，desc="选择 xxx 为 yyy"

【任务3：优化描述（desc 严禁写成 keyword 名称）】
- desc 必须包含元素名称/文本和输入值，严禁写成简单的 keyword 名称
- 正确示例：
  - fill_value: "在 '用户名' 输入框输入 'admin'"
  - click_ele: "点击 '登录' 按钮"
  - press_key: "按 Enter 键提交搜索"
  - hover: "悬停到 '编辑' 图标"
  - open_url: "打开登录页面"
- 错误示例（严禁）："元素输入"、"点击元素"、"键盘按键"、"鼠标悬停"
- 每条 desc 不超过30字，中文自然语言

【任务4：定位表达式（params.locator）智能选择】
- value、index、timeout、url 等其他 params 字段必须与对应原始步骤一致，禁止修改
- drag_and_drop 步骤必须保留 params.start_selector 与 params.end_selector，禁止修改或删除
- params.locator 允许从该步骤「候选定位」列表中重新选择更稳的一项；**禁止**自造不在列表中的表达式
- 选择原则：优先 data-testid / #id；页面上有多个相似按钮（如同时存在「设置」与「基础设置」）时，locator 必须与 desc 中的目标名称一致
- 常见短词（设置、登录、提交等）且存在区域链式候选（如 header >> get_by_text=设置）时，优先选区域链式而非裸 get_by_text
- 若不确定，保持原 locator 不变

========== keyword 映射表（必须严格使用） ==========
open_url → 访问页面url
click_ele → 点击元素
fill_value → 元素输入
wait_for_time → 强制等待时间
hover → 鼠标悬停到元素上方
press_key → 键盘按键
scroll → 滚动页面
mouse_click → 鼠标点击
upload_file → input文件上传
drag_and_drop → 拖拽元素
assert_text → 断言文本存在
assert_ele → 断言元素存在
select_option → 下拉框选择
switch_frame → 切换iframe
close_page → 关闭页面

========== 删减原则示例 ==========
原始（10步）：
1. open_url: https://example.com/ （打开首页，自动重定向到登录页）
2. open_url: https://example.com/login （这是自动重定向，不是手动输入）
3. fill_value: 输入用户名
4. fill_value: 输入密码
5. wait_for_time: 等待9秒（用户自然停顿，多余）
6. click_ele: 点击登录
7. open_url: https://example.com/ （登录成功后自动跳转回首页，多余）
8. click_ele: 点击控制台
9. fill_value: 输入名称
10. click_ele: 点击搜索按钮

优化后（6步）：
1. open_url: https://example.com/
2. fill_value: 输入用户名
3. fill_value: 输入密码
4. click_ele: 点击登录
5. click_ele: 点击控制台
6. fill_value: 输入名称

注意：如果原始步骤中有 hover（如"悬停到知识库卡片"）和 hover 后的 wait_for_time，必须保留，因为悬浮菜单的显示依赖 hover。

========== 约束规则（必须严格遵守） ==========
1. 返回精简后的步骤数组，每个步骤必须包含 method、desc、params、keyword 字段
2. 【硬性指标】优化后的步骤数量必须明显少于原始步骤（通常减少 30%~50%），如果数量一样说明你偷懒了
3. keyword 必须严格使用上面的映射表，不要自己编造
4. 不要添加原始步骤中没有的操作
5. 不要编造不存在的页面元素
6. 描述使用中文，简洁完整
7. 直接输出纯 JSON，严禁使用 markdown 代码块（```json）

返回格式：
{"steps": [{"method": "open_url", "desc": "打开登录页面", "params": {"url": "..."}, "keyword": "访问页面url"}, ...]}

不要输出任何解释性文字，只输出 JSON。""",
            "examples": [],
        },
        "ui_record_append_assertions": {
            "name": "录制步骤-补充断言",
            "scene_type": "ui_case",
            "description": "基于功能用例预期与录制页面文本，为已精简的操作步骤补充断言（支持操作前/后/中间插入）",
            "system_prompt": (
                "你是 UI 自动化测试断言设计专家。"
                "根据测试描述中的「预期结果」和录制期间页面可见文本，生成少量高价值断言步骤。"
                "你必须区分正向断言（应出现）与否定断言（不应出现/不可见/不存在）。"
                "否定断言不可一律用 hidden：不存在用 not_exist，不可见用 not_visible，CSS 隐藏用 hidden。"
                "你只能输出断言步骤，不能修改已有操作。"
                "每条断言必须指定 placement（before/after）和 anchor_step（对应操作步骤序号）。"
                "断言 params.locator 必须优先从「已精简的操作步骤」中对应 fill/click 步骤复制（#id 最佳）。"
                "input 的 placeholder 用 get_by_placeholder=，关联 label 用 get_by_label=；禁止对 placeholder 使用 get_by_text=。"
                "禁止在每次输入/点击前对输入框、按钮做可见性断言；仅 after 关键业务结果（登录成功、查询结果、保存成功等）。"
                "输出纯 JSON，不要 Markdown 代码块。"
            ),
            "user_prompt_template": """测试描述：
{{description}}

提取到的预期结果：
{{expectations_text}}

已精简的操作步骤（共 {{steps_count}} 步，勿修改）：
{{steps_text}}

{% if has_page_context %}录制期间页面可见文本与定位（重要，断言 locator 应优先匹配此处）：
{{page_context}}
{% else %}（未提供页面文本快照，仅根据描述与操作步骤推断）
{% endif %}

========== 任务：生成断言步骤（仅新增断言，不改已有操作） ==========

【规则】
1. **硬性上限**：本次最多生成 {{max_assertions}} 条断言，不得超过；无明确「预期：」时仅对登录成功、查询结果、保存成功等主要节点各 1 条 after 断言
2. **禁止**：在 fill_value/输入操作之前对「请输入xxx」、用户名/密码输入框做 kw_assert_visible
3. 每条断言必须包含 placement 和 anchor_step（对应上方「已精简的操作步骤」序号，从 1 开始）：
   - **before**：仅当描述明确要求「操作前应可见」时使用（默认少用）
   - **after**：操作后验证（点击菜单、提交、跳转、查询、保存后的结果，优先）
4. **正向 vs 否定断言选型（重要）**：
   | 业务语义 | method | 适用场景 |
   |---------|--------|---------|
   | 应出现/可见 | kw_assert_visible | 菜单项、按钮、提示文案应展示 |
   | 文本等于 | kw_assert_element_text | 断言元素文本为某值 |
   | **不存在** | kw_assert_not_exist | 「菜单中无该项」「列表不包含 X」—— DOM 匹配数必须为 0 |
   | **不可见** | kw_assert_not_visible | 元素可能在 DOM 中，但对用户不可见（遮挡/opacity/折叠区未展开） |
   | **隐藏** | kw_assert_hidden | CSS hidden、display:none 或未挂载（Playwright hidden） |
   | 页面 URL | kw_assert_page_url | 跳转后 URL |
   | 页面标题 | kw_assert_page_title | 标题变化 |
   **禁止**：把「不存在/不应出现」仅写成 kw_assert_visible 的反向描述；必须显式用否定 method。
   **「仅显示 A、B」类预期**：对 A、B 各生成 kw_assert_visible（after 打开菜单的操作），对描述中明确不应出现的项生成 kw_assert_not_exist。
5. params.locator **必须从已精简步骤复制**：优先 #id / 步骤里已有 locator；placeholder 用 get_by_placeholder=；禁止 get_by_text=请输入…
6. 菜单/按钮等可见文案才用 get_by_text=；预期含具体名称时 locator 须含该关键词
7. 不要重复已有操作步骤；无明确预期时返回 {"assertions": []} 亦可
8. 每条 desc 为中文，不超过 30 字，且应描述业务结果而非「某输入框可见」

【示例】
- 点击「+」后菜单应出现：placement=after, anchor_step=9, kw_assert_visible, get_by_text=在线文档
- 菜单中不存在「新建目录」：placement=after, anchor_step=9, kw_assert_not_exist, get_by_text=新建目录
- 元素在 DOM 但被遮挡不可见：kw_assert_not_visible（不是 not_exist）
- CSS 折叠隐藏：kw_assert_hidden

【keyword 映射】
kw_assert_visible → 断言元素可见
kw_assert_element_text → 断言元素文本值
kw_assert_not_exist → 断言元素不存在
kw_assert_not_visible → 断言元素不可见
kw_assert_hidden → 断言元素隐藏
kw_assert_page_url → 断言页面url地址
kw_assert_page_title → 断言页面标题

返回格式：
{"assertions": [
  {"method": "kw_assert_visible", "desc": "断言在线文档选项可见", "placement": "after", "anchor_step": 9, "params": {"locator": "get_by_text=在线文档", "index": 1}, "keyword": "断言元素可见"},
  {"method": "kw_assert_not_exist", "desc": "断言菜单无新建目录", "placement": "after", "anchor_step": 9, "params": {"locator": "get_by_text=新建目录"}, "keyword": "断言元素不存在"}
]}

若无合适断言可生成，返回 {"assertions": []}
不要输出解释文字。""",
            "examples": [],
        },
        "qa_judge": {
            "name": "问答准确性评判",
            "scene_type": "qa_eval",
            "description": (
                "RAG 评测公式 v2（范畴+完整性+准确性+表达，0~1 分 + 5 级等级）。"
                "变量：question=问题，ground_truth=标准答案，answer=实际回答（被测 API 或导入）"
            ),
            "system_prompt": (
                "你是企业知识库问答质量评审专家。"
                "必须严格按用户给出的分项公式与 5 级等级映射执行评估，"
                "仅输出 1 个 JSON 对象（不要 Markdown 代码块）。"
            ),
            "user_prompt_template": "",
            "examples": [],
        },
    }

    @classmethod
    def _qa_judge_pro_user_template(cls) -> str:
        from app.core.qa_judge_prompt import QA_JUDGE_USER_PROMPT_TEMPLATE

        return QA_JUDGE_USER_PROMPT_TEMPLATE

    @classmethod
    def _resolve_default_template(cls, code: str) -> dict | None:
        data = cls.DEFAULT_TEMPLATES.get(code)
        if not data:
            return None
        out = dict(data)
        if code == "qa_judge":
            if is_community_edition():
                out.update(
                    description=QA_JUDGE_DESCRIPTION_CE,
                    system_prompt=QA_JUDGE_SYSTEM_PROMPT_CE,
                    user_prompt_template=QA_JUDGE_USER_PROMPT_TEMPLATE_CE,
                )
            else:
                out["user_prompt_template"] = cls._qa_judge_pro_user_template()
        return out

    @classmethod
    async def get_template(cls, code: str) -> dict:
        """
        获取指定模板的完整内容
        用户自定义模板优先；默认模板始终使用代码中的最新版本（确保代码更新即时生效）
        """
        db_template = await AiPromptTemplate.filter(
            code=code, is_enabled=True
        ).first()

        # 如果数据库存在用户自定义模板（非默认），使用数据库版本
        if db_template and not db_template.is_default:
            return {
                "code": db_template.code,
                "name": db_template.name,
                "scene_type": db_template.scene_type,
                "description": db_template.description,
                "system_prompt": db_template.system_prompt,
                "user_prompt_template": db_template.user_prompt_template,
                "examples": db_template.examples,
                "version": db_template.version,
                "is_default": False,
            }

        default = cls._resolve_default_template(code)
        if not default:
            raise ValueError(f"未知的 Prompt 模板编码: {code}")

        # 默认模板始终使用代码中的最新版本，覆盖数据库中的旧版本
        return {
            "code": code,
            "name": default["name"],
            "scene_type": default["scene_type"],
            "description": default["description"],
            "system_prompt": default["system_prompt"],
            "user_prompt_template": default["user_prompt_template"],
            "examples": default["examples"],
            "version": 1,
            "is_default": True,
        }

    @classmethod
    async def render(cls, code: str, context: dict) -> tuple[str, str]:
        """
        渲染 Prompt，返回 (system_prompt, user_prompt)
        :param code: 模板编码
        :param context: Jinja2 渲染变量
        """
        import logging
        logger = logging.getLogger(__name__)
        try:
            template_data = await cls.get_template(code)
            system = template_data["system_prompt"]
            user_template_text = template_data["user_prompt_template"]
            logger.warning(f"[render] code={code}, template_length={len(user_template_text)}, context_keys={list(context.keys())}")
            if not user_template_text:
                raise ValueError(f"模板 {code} 的 user_prompt_template 为空")
            user_template = Jinja2Template(user_template_text)
            user = user_template.render(**context)
            logger.warning(f"[render] 渲染成功, user_prompt_length={len(user)}")
            return system, user
        except Exception as e:
            logger.error(f"[render] 渲染模板失败: code={code}, error={e}", exc_info=True)
            raise ValueError(f"渲染模板失败: {str(e)}")

    @classmethod
    async def ensure_initialized(cls):
        """
        惰性初始化预置模板到数据库（若不存在或内容有更新）
        在首次访问 Prompt 相关接口时自动调用
        """
        global _prompt_initialized
        if _prompt_initialized:
            return
        for code in cls.DEFAULT_TEMPLATES:
            data = cls._resolve_default_template(code)
            if not data:
                continue
            template = await AiPromptTemplate.filter(code=code).first()
            if not template:
                # 不存在则创建
                await AiPromptTemplate.create(
                    name=data["name"],
                    code=code,
                    description=data["description"],
                    scene_type=data["scene_type"],
                    system_prompt=data["system_prompt"],
                    user_prompt_template=data["user_prompt_template"],
                    examples=data.get("examples", []),
                    is_default=True,
                    is_enabled=True,
                )
            elif template.is_default:
                # 仅当用户未自定义时才同步更新默认模板内容
                # 检测内容是否有变化
                has_changed = (
                    template.system_prompt != data["system_prompt"]
                    or template.user_prompt_template != data["user_prompt_template"]
                    or template.name != data["name"]
                    or template.description != data["description"]
                )
                if has_changed:
                    template.system_prompt = data["system_prompt"]
                    template.user_prompt_template = data["user_prompt_template"]
                    template.name = data["name"]
                    template.description = data["description"]
                    template.examples = data.get("examples", [])
                    template.version += 1
                    await template.save()
        _prompt_initialized = True

    @staticmethod
    def extract_variables(template_text: str) -> list[str]:
        """
        从 Jinja2 模板中提取 {{变量名}} 变量列表
        """
        pattern = r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}"
        matches = re.findall(pattern, template_text)
        return list(dict.fromkeys(matches))  # 去重并保持顺序
