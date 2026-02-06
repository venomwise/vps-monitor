# VPS 监控系统

轻量级 VPS 监控系统，实时监控系统资源和 Docker 容器状态，通过企业微信机器人发送告警通知。

## 功能特性

- **系统监控**: CPU、内存、磁盘、Swap 使用率监控
- **网络监控**: 网络流量、连接数监控
- **Docker 监控**: 容器运行状态、健康检查监控
- **告警通知**: 企业微信机器人告警，支持告警冷却和恢复通知
- **定时报告**: 基于 Cron 表达式的定时状态报告
- **systemd 服务**: 开机自启，自动重启

## 快速开始

### 一键安装（推荐）

```bash
curl -fsSL https://raw.githubusercontent.com/venomwise/vps-monitor/main/install.sh | sudo bash
```

一键安装会自动完成：
- 下载程序文件到 `/opt/vps-monitor/`
- 安装 Python 依赖
- 配置 systemd 服务

安装完成后，编辑配置文件并启动服务：

```bash
sudo vim /opt/vps-monitor/config.yaml  # 填入企业微信 Webhook URL
sudo systemctl start vps-monitor
```

**更新程序**：再次运行一键安装命令即可，配置文件会保留。

---

### 手动安装

#### 1. 安装依赖

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install python3 python3-pip curl

# 安装 Python 依赖
pip3 install -r requirements.txt
```

#### 2. 配置

编辑 `config.yaml` 文件：

```yaml
# 企业微信机器人配置（必填）
wechat:
  webhook_url: "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY"

# Docker 容器监控（按需配置）
docker:
  enabled: true
  containers:
    - name: "nginx"
      check_health: true
    - name: "mysql"
      check_health: true
```

#### 3. 安装服务

```bash
sudo ./install.sh
```

#### 4. 启动服务

```bash
sudo systemctl start vps-monitor
sudo systemctl status vps-monitor
```

## 配置说明

### 基础配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `general.hostname` | 自动获取 | 主机名，留空自动获取 |
| `general.check_interval` | 900 | 检查间隔（秒） |
| `general.alert_cooldown` | 300 | 告警冷却时间（秒） |
| `general.send_recovery` | true | 是否发送恢复通知 |
| `general.log_level` | INFO | 日志级别 |

### 监控阈值

| 指标 | 默认阈值 | 说明 |
|------|----------|------|
| 内存使用率 | 80% | 超过阈值触发告警 |
| 磁盘使用率 | 80% | 超过阈值触发告警 |
| CPU 使用率 | 80% | 超过阈值触发告警 |
| Swap 使用率 | 80% | 超过阈值触发告警 |
| 网络流量 | 100 Mbps | 超过阈值触发告警 |
| 连接数 | 1000 | 超过阈值触发告警 |

### 定时报告

```yaml
scheduled_report:
  enabled: true
  cron: "0 9 * * *"  # 每天 9:00
```

常用 Cron 表达式：
- `0 9 * * *` - 每天 9:00
- `0 9,18 * * *` - 每天 9:00 和 18:00
- `0 */6 * * *` - 每 6 小时
- `0 9 * * 1` - 每周一 9:00

## 常用命令

```bash
# 启动服务
sudo systemctl start vps-monitor

# 停止服务
sudo systemctl stop vps-monitor

# 重启服务
sudo systemctl restart vps-monitor

# 查看状态
sudo systemctl status vps-monitor

# 查看日志
sudo journalctl -u vps-monitor -f

# 查看应用日志
tail -f /opt/vps-monitor/logs/monitor.log
```

## 卸载

```bash
sudo ./uninstall.sh
```

## 文件结构

```
/opt/vps-monitor/
├── monitor.py          # 入口文件（保持兼容）
├── vps_monitor/        # 核心业务模块
│   ├── app.py          # 主监控编排
│   ├── config.py       # 配置管理
│   ├── notifier.py     # 企业微信通知
│   ├── state.py        # 告警状态持久化
│   ├── scheduler.py    # 定时报告调度
│   └── collectors/     # 指标采集器
│       ├── system.py
│       ├── network.py
│       └── docker.py
├── config.yaml         # 配置文件
├── requirements.txt    # Python 依赖
├── alert_state.json    # 告警状态（运行时生成）
└── logs/
    └── monitor.log     # 日志文件
```

## 开发说明

- 运行入口保持不变：`python3 monitor.py`
- `monitor.py` 仅负责启动流程，业务逻辑位于 `vps_monitor/` 包内
- 扩展监控能力时，优先在 `vps_monitor/collectors/` 中新增或修改采集器

## 消息格式示例

### 告警消息
```
⚠️ VPS 告警 [hostname]
━━━━━━━━━━━━━━━━
📊 内存使用率: 85.2% (阈值: 80%)
⏰ 时间: 2026-02-04 15:30:00
```

### 恢复消息
```
✅ VPS 恢复 [hostname]
━━━━━━━━━━━━━━━━
📊 内存使用率: 72.1% (已恢复正常)
⏰ 时间: 2026-02-04 15:45:00
```

### 定时状态报告
```
📊 VPS 状态报告 [hostname]
━━━━━━━━━━━━━━━━━━━━━━
🖥️ 系统状态
  • CPU: 23.5%
  • 内存: 65.2% (2.1GB / 3.2GB)
  • Swap: 12.0%
  • 磁盘(/): 45.8% (18.3GB / 40GB)

🌐 网络状态
  • 入站: 2.3 Mbps
  • 出站: 1.1 Mbps
  • 连接数: 156

🐳 Docker 容器
  • nginx: ✅ running (healthy)
  • mysql: ✅ running (healthy)

⏰ 报告时间: 2026-02-04 09:00:00
```

## 常见问题

### 1. Docker 监控不可用

确保：
- Docker 服务已启动
- 监控程序有权限访问 Docker socket
- 已安装 docker Python 库

### 2. 网络连接数获取失败

获取网络连接数需要 root 权限，确保服务以 root 用户运行。

### 3. 企业微信通知发送失败

检查：
- Webhook URL 是否正确
- 服务器是否能访问企业微信 API
- 机器人是否被禁用

## License

MIT
