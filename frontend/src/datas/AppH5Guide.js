/** App H5 / WebView / 手机 Chrome 使用说明与示例（供 UI 折叠面板展示） */

export const APP_DRIVER_MODE_HINTS = [
  { value: 'hybrid', label: '混合（推荐）', desc: '原生控件 + 图像识别混跑；不含 H5 DOM 操作。' },
  { value: 'hybrid_web', label: '混合 WebView', desc: 'Hybrid App 内嵌 H5 + 原生/图像混跑；需 App 开启 WebView 调试。' },
  { value: 'mobile_chrome', label: '手机 Chrome H5', desc: '真机 Chrome 浏览器打开的 H5 + 原生/图像混跑。' },
  { value: 'native', label: '仅控件', desc: '只使用 resource_id / text 等原生定位，不支持图像步骤。' },
  { value: 'vision', label: '偏图像', desc: '以图像识别为主，可与少量原生步骤混用。' },
]

export const APP_H5_COMMON_NOTES = [
  '含 H5 定位（context: webview 或 css/id）时，驱动模式必须为「混合 WebView」或「手机 Chrome H5」。',
  'H5 步骤前建议先加「切换 WebView」或「切换 Chrome」，并确认 page_index 与元素探查中一致。',
  '日常桌面 H5 功能回归请用「Web UI 自动化」；真机布局/兼容性再用本模块。',
  '微信内置浏览器、小程序 WebView 通常不支持标准 CDP，请勿使用本方案。',
]

export const APP_WEBVIEW_EXAMPLE_STEPS = `[
  { "keyword": "启动应用", "method": "launch_app", "params": { "app_id": "com.example.app" } },
  { "keyword": "切换 WebView", "method": "switch_webview", "params": { "page_index": 0, "url": "m.example.com" } },
  { "keyword": "点击元素", "method": "click_element", "params": {
      "locator": { "context": "webview", "by": "css", "value": "#login-btn", "index": 1 },
      "timeout": 15
  }}
]`

export const APP_CHROME_EXAMPLE_STEPS = `[
  { "keyword": "打开链接", "method": "open_url", "params": { "url": "https://m.example.com/login" } },
  { "keyword": "切换 Chrome", "method": "switch_chrome", "params": { "page_index": 0, "url": "m.example.com" } },
  { "keyword": "输入文本", "method": "input_text", "params": {
      "locator": { "context": "webview", "by": "css", "value": "input[name=username]", "index": 1 },
      "text": "test_user", "timeout": 15
  }}
]`

export const APP_INSPECTOR_STEPS = [
  '选择在线 App Runner；本机 adb devices 须为 device（USB / WiFi / 模拟器均可，见执行器安装指南）。',
  '原生页：刷新控件树 → 点击截图选控件 → 保存到元素库。',
  'App 内 H5：检测到 WebView 后，H5 来源选「App WebView」→ 选 Tab → 探测 H5 DOM。',
  '手机 Chrome H5：先在 Chrome 打开页面，H5 来源选「手机 Chrome」→ 探测 DOM。',
  '保存的 H5 元素在用例中通过「元素库引用」或复制定位器使用。',
]

export const APP_ELEMENT_H5_NOTES = [
  'H5 元素请设上下文为 WebView，定位方式用 css / xpath / text / id。',
  '建议在元素探查探测 DOM 后直接保存，page_index 与用例里「切换 WebView/Chrome」保持一致。',
  'App 内 H5 用例驱动模式选 hybrid_web；手机 Chrome 用例选 mobile_chrome。',
]

export const APP_ELEMENT_VISION_NOTES = [
  '图像识别元素请上传清晰、特征明显的 UI 局部截图（按钮/图标等，建议 PNG，≤2MB），不要上传整页截图。',
  '相似度阈值默认 0.8；匹配不稳定时可略降到 0.7，或开启 RGB 匹配。',
  '正式包 WebView 调试关闭时，H5 DOM 不可用，可用识别小图点击按钮/图标。',
  '步骤中可引用元素库 image 元素，驱动模式须为 hybrid / vision / hybrid_web / mobile_chrome。',
  '跨分辨率时建议填写「中心偏移」「录制分辨率」；元素探查框选保存会自动带入。',
]

export const APP_VISION_EXAMPLE_STEPS = `[
  { "keyword": "点击元素", "method": "click_element", "params": {
      "locator_ref": "登录按钮",
      "timeout": 15
  }},
  { "keyword": "等待元素", "method": "wait_element", "params": {
      "locator": { "by": "image", "value": "app-elements/1/xxx.png", "threshold": 0.8 },
      "timeout": 10
  }}
]`

export const APP_STEP_CONTEXT_HINTS = {
  switch_webview: '连接 App 内 WebView。page_index 与元素探查「App WebView」下列表索引一致；url 可填 URL 片段辅助匹配 Tab。',
  switch_chrome: '连接手机 Chrome Tab。请先用「打开链接」或手动在 Chrome 打开 H5；page_index 与元素探查「手机 Chrome」列表一致。',
  switch_native: '断开 CDP，后续步骤回到 u2 原生上下文。',
  open_url: '通过 Intent 打开手机默认浏览器（通常为 Chrome）。mobile_chrome 用例中常作为第一步打开 H5。',
  h5_locator: 'H5 定位器需对应用例驱动模式 hybrid_web 或 mobile_chrome；建议前面已有切换 WebView/Chrome 步骤。',
  image_locator: '图像识别：上传识别小图或引用元素库；驱动模式不能为 native。阈值默认 0.8，失败时可看报告中的最高相似度。',
}
