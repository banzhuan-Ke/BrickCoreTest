# Mock 服务

> 接口自动化总览见 [接口自动化](./api-automation.md)。本文专讲 **Mock 假被测服务** 的配置、调用与同路径多场景。

## 适用场景

下游接口未就绪、或要在调试/套件里固定返回时：在平台配置方法、路径与响应，用接口调试 / Postman / curl 去打调用地址，即可拿到预设 JSON。

**路径**：**接口自动化 → Mock 服务**

## 快速上手

1. 新建 Mock：选 **方法**、填 **匹配路径**、写 **响应 Body**（填什么就返回什么，不必再包 `status_code` 外壳）
2. 调用：`{平台}/api-module/mock-call/{匹配路径}`（方法必须与配置一致）
3. 同 URL 要多种返回：建 **多条** Mock（方法+路径相同），用 **高级匹配** 分流；可用列表 **复制为新场景** 少填一遍

## 字段说明

| 字段 | 说明 |
|------|------|
| 请求方法 | `GET` / `POST` / `PUT` / `DELETE` / `PATCH`；**调用时必须一致** |
| 匹配路径 | 如 `/api/order`（可带或不带前导 `/`） |
| 响应状态码 | HTTP 状态码（如 `200`、`400`） |
| 响应 Headers | 可选；键值 JSON |
| 响应 Body | 返回给调用方的正文（object / array / 字符串均可） |
| 延迟(ms) | 模拟慢接口 |
| 高级匹配 `match_rules` | 同路径多场景：按 **header / query / body** 命中不同 Mock |

## 调用地址

```text
{平台地址}/api-module/mock-call/{匹配路径}
```

可选 `?_project_id=项目ID`（多项目同路径时建议加上）。

| 场景 | 请求示例 |
|------|----------|
| GET | `GET https://example.com/api-module/mock-call/api/hello` |
| POST | `POST …/mock-call/api/login` + JSON Body |
| 带 query | `POST …/mock-call/api/order?type=1` |

接口调试：Base URL 填 `{平台}/api-module/mock-call`，Path 填 `/api/order`，**不必**填平台登录 Token。

> **鉴权**：调用 `/api-module/mock-call/...` **免平台 JWT**（按配置的方法/路径/高级匹配即可命中）；Mock 管理页的新建/编辑/删除仍需登录与权限。请勿在响应体里写真实密钥。

## 示例 1：最简单的 GET

| 项 | 值 |
|----|-----|
| 方法 | `GET` |
| 路径 | `/api/hello` |
| 状态码 | `200` |
| 响应 Body | `{"code":0,"msg":"ok","data":"hello"}` |
| 高级匹配 | `{}` |

```bash
curl "https://example.com/api-module/mock-call/api/hello"
```

## 示例 2：POST（方法要对上）

| 项 | 值 |
|----|-----|
| 方法 | **`POST`** |
| 路径 | `/api/login` |
| 响应 Body | `{"code":0,"token":"mock-token","user":"demo"}` |

```bash
curl -X POST "https://example.com/api-module/mock-call/api/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"a","password":"b"}'
```

Mock 配 GET、调用发 POST → **404**。

## 示例 3：同路径、不同配置 → 不同返回（重点）

**先弄清三点：**

1. 要建 **多条 Mock 记录**（不是一条里写多种返回）。后续「一条多场景」见规划 **API-6**；当前用 **复制为新场景**。
2. 这几条的 **方法 + 路径必须相同**。
3. **名称建议不同**；系统靠高级匹配分流，不靠名称。

**推荐**：建好第 1 条 → 列表「复制为新场景」→ 改名称 / 匹配 / Body → 再复制出兜底条。

匹配：规则更具体的优先；可留一条 `match_rules` 为 `{}` 作默认。

### 第 1 条 · 订单-待支付

| 项 | 值 |
|----|-----|
| 名称 | `订单-待支付` |
| 方法 / 路径 | `POST` / `/api/order` |
| 响应 Body | `{"code":0,"scene":"pending","amount":99}` |

```json
{
  "query": {"type": "1"},
  "body": {"status": "pending"}
}
```

### 第 2 条 · 订单-已支付

| 项 | 值 |
|----|-----|
| 名称 | `订单-已支付` |
| 方法 / 路径 | `POST` / `/api/order` |
| 高级匹配 | `{"query": {"type": "2"}}` |
| 响应 Body | `{"code":0,"scene":"paid","amount":199}` |

### 第 3 条 · 订单-默认（可选）

| 项 | 值 |
|----|-----|
| 名称 | `订单-默认` |
| 方法 / 路径 | `POST` / `/api/order` |
| 高级匹配 | `{}` |
| 响应 Body | `{"code":0,"scene":"default"}` |

列表应看到 **3 行**，方法/路径相同、名称不同。

```bash
# 待支付
curl -X POST "https://example.com/api-module/mock-call/api/order?type=1" \
  -H "Content-Type: application/json" \
  -d '{"status":"pending"}'

# 已支付
curl -X POST "https://example.com/api-module/mock-call/api/order?type=2" \
  -H "Content-Type: application/json" -d '{}'

# 兜底
curl -X POST "https://example.com/api-module/mock-call/api/order?type=9" \
  -H "Content-Type: application/json" -d '{}'
```

| 请求 | 命中 |
|------|------|
| `?type=1` + Body `status:pending` | 订单-待支付 |
| `?type=2` | 订单-已支付 |
| 其它（有兜底时） | 订单-默认 |
| 无匹配且无兜底 | `404` |

`match_rules` 维度：

| 键 | 匹配对象 | 说明 |
|----|----------|------|
| `query` | URL 查询参数 | 按字符串比（`type=1` 配 `"1"`） |
| `body` | JSON 请求体**顶层**字段 | POST/PUT 等 |
| `header` | 请求头 | 如 `{"X-Mock-Scene": "A"}` |

可只配一个维度，例如：

```json
{"header": {"X-Mock-Scene": "error"}}
```

## 常见问题

**Q：是建三条同名 Mock 吗？**  
是三条**独立记录**；方法+路径相同，名称建议不同。用「复制为新场景」可少填一遍。

**Q：好像只能 GET，POST 一直 404？**  
检查列表里方法是否为 `POST`；调用方法须与配置一致。

**Q：高级匹配配了却总 404？**  
核对 query / body / header 是否全部满足；可先清空为 `{}` 验证路径能通。

**Q：调用还返回 401？**  
升级到含 **API-5** 的 Backend 后，调用本身不应再因平台登录失败。若仍 401：确认路径是 `/api-module/mock-call/...`（不是 `/api-module/mock` 管理 API）；旧版本需重启升级后的 Backend。

**Q：浏览器打开一堆 HTML？**  
多半打到前端路由；请用完整路径 `/api-module/mock-call/...`，并确认 Nginx 已把 `/api-module` 反代到 Backend。

## 相关规划（研发备忘）

| ID | 说明 |
|----|------|
| **API-5** | ✅ Mock 调用免登（管理 CRUD 仍鉴权） |
| **API-6** | 一条维护多场景 — 见 `api-mock-multi-scene-plan.md`；当前用「复制为新场景」过渡 |
