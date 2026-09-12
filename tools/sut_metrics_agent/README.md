# BrickCore 被测监控采集器（PERF-1）

装在**被测机或演示机宿主机**上，向测试平台上报主机指标。  
**不要**装在压测施压机（JMeter / BrickCorePerf / Runner 施压节点）上。

## 采什么指标

| 指标 | 说明 |
|------|------|
| **CPU %** | 整机 CPU 使用率 |
| **内存 %** | 整机内存使用率 |
| 内存已用 / 总量 MB | 随点上报 |
| **磁盘 %** | 根分区（Windows 为系统盘）占用 |
| **网卡收/发 KB/s** | 相对上一采样的速率 |
| 磁盘读/写 KB/s | 随点上报（详情可扩展展示） |
| load1 | Linux 1 分钟负载（有则上报） |

当前 **没有** 进程级、容器 cgroup、GPU 等。  
装在宿主机采的是宿主机；装进应用容器内看到的可能是宿主机 `/proc`，**勿当成 Pod 指标**。

## 快速开始（推荐：脚本一键启停）

1. 平台「性能测试 → 被测服务器」创建一台，**复制 Token**。
2. 将本目录拷到被测机，例如 `/opt/sut_metrics_agent`。
3. 启动（首次会交互询问平台地址、Token；下次可选「用上次」或「只更新 Token」）：

```bash
cd /opt/sut_metrics_agent
chmod +x start.sh stop.sh
./start.sh
# 看日志
tail -f agent.log
# 停止
./stop.sh
```

Windows：双击或运行 `start.bat` / `stop.bat`。

脚本会自动创建 `.venv` 并安装依赖；配置写入 `agent_config.json`（权限 600）。

### 若 `./start.sh` 报 `bash\r: No such file or directory`

说明 `start.sh` / `stop.sh` 被打成了 Windows 换行（CRLF）。在被测机上修一次即可：

```bash
sed -i 's/\r$//' start.sh stop.sh
chmod +x start.sh stop.sh
./start.sh
```

或绕过 shell 脚本直接：

```bash
.venv/bin/python agent_ctl.py start
# 未建 venv 时：python3 agent_ctl.py start
```

**打包给 Linux 用时**请用仓库脚本（保证 `.sh` 为 LF、不含 `__pycache__`/venv）：

```bash
python tools/sut_metrics_agent/pack_zip.py -o /tmp/sut_metrics_agent.zip
```

勿用 Windows 资源管理器 / `Compress-Archive` 直接压整个目录（易带 CRLF 与反斜杠路径）。

### 手动方式（虚拟环境）

```bash
cd /opt/sut_metrics_agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp agent_config.example.json agent_config.json
# 编辑 platform、token；HTTP 非本机须 allow_insecure_http=true
python sut_metrics_agent.py -c agent_config.json
# 或：python agent_ctl.py start
```
配置示例：

```json
{
  "platform": "http://47.111.226.241",
  "token": "<粘贴一次性 Token>",
  "allow_insecure_http": true,
  "interval_sec": 5,
  "upload_every_sec": 15,
  "buffer_hours": 48,
  "data_dir": "./data"
}
```

- `platform`：平台根地址，**无尾斜杠**；经 Nginx 时一般不要写 `:8000`。
- 非本机 **HTTP** 必须 `"allow_insecure_http": true`（Token 明文，仅联调）；生产优先 HTTPS。
- 列表出现 **在线**、详情有曲线即成功。若 `sample_allowed=False`，到控制台打开「启用监控」或检查日程。

## 后台常驻

前台 `Ctrl+C` 会停。确认无误后任选一种：

### nohup（最快）

```bash
cd /opt/sut_metrics_agent
mkdir -p data
nohup .venv/bin/python sut_metrics_agent.py -c agent_config.json \
  >> /var/log/sut_metrics_agent.log 2>&1 &
echo $! > /var/run/sut_metrics_agent.pid
tail -f /var/log/sut_metrics_agent.log
```

停止：

```bash
kill "$(cat /var/run/sut_metrics_agent.pid)"
# 或：pkill -f 'sut_metrics_agent.py'
```

### systemd（推荐生产）

`/etc/systemd/system/sut-metrics-agent.service`：

```ini
[Unit]
Description=BrickCore 被测监控采集器
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/sut_metrics_agent
ExecStart=/opt/sut_metrics_agent/.venv/bin/python /opt/sut_metrics_agent/sut_metrics_agent.py -c /opt/sut_metrics_agent/agent_config.json
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable --now sut-metrics-agent
systemctl status sut-metrics-agent
journalctl -u sut-metrics-agent -f
```

### Windows

任务计划程序「登录时启动」，或：

```bat
start /B .venv\Scripts\pythonw.exe sut_metrics_agent.py -c agent_config.json
```

## 配置项

| 字段 | 说明 |
|------|------|
| `platform` | 平台根 URL，`http(s)://host`，无尾斜杠 |
| `token` | `X-SUT-Token`，**勿放 URL Query** |
| `allow_insecure_http` | 非本机 HTTP 时必须为 `true` |
| `interval_sec` | 采样间隔，**2～60**，默认 5；**可在平台「被测服务器 → 采集参数」下发**，约 30s 内心跳热更新并回写本文件 |
| `upload_every_sec` | 批量上传间隔，须 ≥ interval，默认 15；同上可由平台下发 |
| `buffer_hours` | 本地 SQLite 保留时长，默认 **48（2 天）**，**1～168**；同上可由平台下发；平台接受约 **14 天**内补传点（与 `SUT_METRICS_RETAIN_DAYS` / force 历史窗对齐） |
| `data_dir` | SQLite 与 `agent_uid.txt` 目录；相对路径相对**进程 cwd** |

## 行为说明

- 本地 SQLite WAL 缓冲；断网可补传；优先删已上传数据控磁盘。
- 关闭「启用监控」或命中 pause 日程：停采停传，仍约 **30s** 心跳（列表可仍显示在线）。
- 每次请求带本地 `agent_uid`；平台首次激活绑定，**禁止多机共用同一 Token**。
- 心跳带回 `config_rev`、可选 `agent_settings`，以及 `force_until_ms` / `pressure_active`。
- **压测进行中**（平台 `pressure_active=true`，对应仍有 pending/running 绑定）：采样约 **2s**、**本地落库不实时上报**；压测结束后平台立刻把 `pressure_active` 置 false（grace force 仍可接受补传），采集器尽快整批冲刷缓冲，减轻网卡自干扰且不误伤报告再切片。
- **关监控 / 进入 pause** 时丢弃未上传缓冲；仅改采样间隔等参数不丢缓冲。
- 平台下发的 `agent_settings` 会热更新并回写 `agent_config.json`（本地文件为初始值与离线兜底）。
- `SIGTERM` / `SIGINT` 可优雅退出。

## 控制台：「重置采集器」是做什么的？

采集器首次激活会把本机 `agent_uid.txt` 绑到该「被测服务器」。之后换机、删了 `data/`、或重装导致 uid 变了，再用原 Token 会 **409**。

点 **重置采集器** = 清空平台上的绑定，**不删历史曲线、不换 Token**。然后在本机重新跑采集器即可重新激活。  
若 Token 也丢了，用 **轮换 Token**（旧 Token 立即失效）。

## 被测应用（菜单说明）

「被测服务器」= 装了被测监控采集器、真正采 CPU/内存的机器。  
「被测应用」= 配置「压某个业务系统 + 某个环境时，报告该看哪些机器」（**不采数**）：

1. **新建**：填业务系统名称；「机器分工」可选（应用机 / 数据库等标签，与采什么指标无关）。
2. **配机器**：选环境 → 按分工挂被测服务器；同一台机可挂多个业务系统。
3. **预览机器**：核对该环境下会带上哪些机器。

压测场景绑定被测应用后，报告会按施压窗切片展示 CPU/内存曲线（M3）。执行时若机器处于日常暂停日程，平台会短暂 **force** 强制采集。
## 口径说明

| 安装位置 | 采到的大致是 |
|----------|----------------|
| 宿主机 | 主机 CPU / 内存（本采集器目标） |
| 应用容器内 | 可能是宿主机 `/proc`，不是 Pod cgroup |
