# VPS 监控系统实现计划

> **项目目标**: 构建一个轻量级 VPS 监控系统，实时监控系统资源和 Docker 容器状态，通过企业微信机器人发送告警通知，支持定时推送状态报告
> **技术栈**: Python 3.9+ | psutil | docker SDK | PyYAML | requests | croniter
> **部署方式**: systemd 服务

---

## 计划概述

本计划将 VPS 监控系统分为 **4 个阶段**，实现完整的监控、告警、通知、定时报告功能。

---

## 技术选型

| 组件 | 选型 | 理由 |
|-----|-----|-----|
| 运行环境 | Python 3.9+ | Ubuntu/Debian 默认支持，生态丰富 |
| 系统监控 | psutil | 跨平台系统监控库，功能全面 |
| Docker 监控 | docker SDK | 官方 Python SDK，功能完整 |
| 配置管理 | PyYAML | YAML 格式易读易维护 |
| HTTP 请求 | requests | 简单可靠的 HTTP 库 |
| 定时任务 | croniter | 轻量级 Cron 表达式解析库 |
| 服务管理 | systemd | Linux 标准服务管理，开机自启 |

---

## 监控指标汇总

| 类别 | 指标 | 默认阈值 | 说明 |
|------|------|----------|------|
| 系统 | 内存使用率 | 80% | 防止 OOM |
| 系统 | 磁盘使用率 | 80% | 防止磁盘写满 |
| 系统 | CPU 使用率 | 80% | 发现性能瓶颈 |
| 系统 | Swap 使用率 | 80% | 提前发现内存压力 |
| 网络 | 流量 (Mbps) | 100 | 监控流量突增 |
| 网络 | 连接数 | 1000 | 防止连接耗尽 |
| Docker | 运行状态 | running | 容器停止告警 |
| Docker | 健康检查 | healthy | 容器不健康告警 |

---

## 项目结构

```
/opt/vps-monitor/
├── monitor.py              # 主监控脚本
├── config.yaml             # 配置文件
├── requirements.txt        # Python 依赖
├── alert_state.json        # 告警状态文件（运行时生成）
└── logs/                   # 日志目录
    └── monitor.log

/etc/systemd/system/
└── vps-monitor.service     # systemd 服务文件
```

---

## Phase 1: 核心框架 (基础设施)

### 目标
建立项目基础架构，实现配置管理和通知功能。

### 1.1 项目初始化

**任务清单:**
- [ ] 1.1.1 创建项目目录结构
- [ ] 1.2.2 创建 `requirements.txt` 依赖文件
  ```
  psutil>=5.9.0
  pyyaml>=6.0
  requests>=2.28.0
  docker>=6.0.0
  croniter>=1.3.0
  ```
- [ ] 1.1.3 创建配置文件 `config.yaml` 模板

**交付物:**
- 完整的项目目录结构
- 依赖文件

### 1.2 配置管理模块

**任务清单:**
- [ ] 1.2.1 实现 `ConfigManager` 类
  - 加载 YAML 配置文件
  - 配置项验证
  - 默认值处理
- [ ] 1.2.2 实现配置热重载功能（可选）

**交付物:**
- 配置管理模块
- 完整的配置文件模板

### 1.3 企业微信通知模块

**任务清单:**
- [ ] 1.3.1 实现 `WeChatNotifier` 类
  - Webhook API 调用封装
  - 消息格式化（Markdown 格式）
  - 错误处理和重试机制
- [ ] 1.3.2 实现告警消息模板
- [ ] 1.3.3 实现恢复消息模板

**交付物:**
- 企业微信通知模块
- 消息模板

### 1.4 告警状态管理

**任务清单:**
- [ ] 1.4.1 实现 `AlertStateManager` 类
  - 告警状态持久化（JSON 文件）
  - 冷却时间检查
  - 恢复状态检测
- [ ] 1.4.2 实现告警去重逻辑

**交付物:**
- 告警状态管理模块
- 状态持久化文件

### Phase 1 验收标准
- [ ] 配置文件可正常加载
- [ ] 企业微信通知可正常发送
- [ ] 告警冷却机制正常工作

---

## Phase 2: 监控采集器

### 目标
实现所有监控指标的数据采集和阈值判断。

### 2.1 系统监控采集器

**任务清单:**
- [ ] 2.1.1 实现 `SystemCollector` 类
  - 内存使用率采集 (`psutil.virtual_memory()`)
  - 磁盘使用率采集 (`psutil.disk_usage()`)
  - CPU 使用率采集 (`psutil.cpu_percent()`)
  - Swap 使用率采集 (`psutil.swap_memory()`)
- [ ] 2.1.2 实现阈值判断逻辑
- [ ] 2.1.3 实现多磁盘路径监控

**交付物:**
- 系统监控采集器
- 阈值判断功能

### 2.2 网络监控采集器

**任务清单:**
- [ ] 2.2.1 实现 `NetworkCollector` 类
  - 网络流量采集 (`psutil.net_io_counters()`)
  - 流量速率计算（需要两次采样）
  - 网络连接数采集 (`psutil.net_connections()`)
- [ ] 2.2.2 实现流量异常检测
- [ ] 2.2.3 实现连接数阈值判断

**交付物:**
- 网络监控采集器
- 流量速率计算功能

### 2.3 Docker 监控采集器

**任务清单:**
- [ ] 2.3.1 实现 `DockerCollector` 类
  - Docker 客户端初始化
  - 容器状态检查（running/exited/paused）
  - 容器健康状态检查（healthy/unhealthy）
- [ ] 2.3.2 实现指定容器过滤
- [ ] 2.3.3 实现 Docker 服务不可用时的优雅降级

**交付物:**
- Docker 监控采集器
- 容器状态检查功能

### Phase 2 验收标准
- [ ] 所有系统指标可正常采集
- [ ] 网络流量速率计算准确
- [ ] Docker 容器状态检查正常
- [ ] 阈值判断逻辑正确

---

## Phase 3: 主程序与部署

### 目标
整合所有模块，实现完整的监控循环，并部署为 systemd 服务。

### 3.1 主监控程序

**任务清单:**
- [ ] 3.1.1 实现 `VPSMonitor` 主类
  - 初始化所有采集器
  - 实现监控循环
  - 整合告警判断和通知
- [ ] 3.1.2 实现优雅退出（信号处理）
- [ ] 3.1.3 实现日志记录

**交付物:**
- 完整的主监控程序
- 日志系统

### 3.2 systemd 服务配置

**任务清单:**
- [ ] 3.2.1 创建 `vps-monitor.service` 服务文件
  - 配置服务描述
  - 配置启动命令
  - 配置重启策略
  - 配置日志输出
- [ ] 3.2.2 编写安装脚本
- [ ] 3.2.3 编写卸载脚本

**交付物:**
- systemd 服务文件
- 安装/卸载脚本

### 3.3 测试与文档

**任务清单:**
- [ ] 3.3.1 功能测试
  - 各指标采集测试
  - 告警触发测试
  - 恢复通知测试
  - 冷却机制测试
- [ ] 3.3.2 编写使用说明
  - 安装步骤
  - 配置说明
  - 常见问题

**交付物:**
- 测试报告
- 使用文档

### Phase 3 验收标准
- [ ] 监控程序可持续稳定运行
- [ ] systemd 服务可正常启动/停止/重启
- [ ] 开机自启功能正常
- [ ] 告警和恢复通知正常发送

---

## Phase 4: 定时状态报告

### 目标
实现基于 Cron 表达式的定时状态推送功能，主动向企业微信发送完整的 VPS 状态报告。

### 4.1 定时报告模块

**任务清单:**
- [ ] 4.1.1 实现 `ScheduledReporter` 类
  - Cron 表达式解析（使用 croniter）
  - 计算下次执行时间
  - 检查是否到达执行时间
- [ ] 4.1.2 实现状态报告数据收集
  - 调用所有采集器获取当前状态
  - 汇总系统指标（CPU、内存、磁盘、Swap）
  - 汇总网络指标（流量、连接数）
  - 汇总 Docker 容器状态
- [ ] 4.1.3 实现状态报告消息格式化
  - 设计完整状态报告模板
  - 格式化各项指标数据

**交付物:**
- 定时报告模块
- 状态报告消息模板

### 4.2 主程序集成

**任务清单:**
- [ ] 4.2.1 在主监控循环中集成定时报告检查
  - 每次循环检查是否到达 Cron 执行时间
  - 触发状态报告发送
- [ ] 4.2.2 更新配置管理支持 `scheduled_report` 配置段
- [ ] 4.2.3 实现定时报告的启用/禁用控制

**交付物:**
- 集成定时报告的主程序
- 更新后的配置文件模板

### Phase 4 验收标准
- [ ] Cron 表达式可正确解析
- [ ] 定时报告按计划时间准确触发
- [ ] 状态报告包含所有监控指标
- [ ] 定时报告与阈值告警功能互不干扰

---

## 配置文件完整设计

```yaml
# VPS 监控配置文件
# 文件路径: /opt/vps-monitor/config.yaml

# 基础配置
general:
  hostname: ""              # 留空则自动获取主机名
  check_interval: 900       # 检查间隔（秒），默认 15 分钟
  alert_cooldown: 300       # 告警冷却时间（秒），默认 5 分钟
  send_recovery: true       # 是否发送恢复通知
  log_level: "INFO"         # 日志级别: DEBUG, INFO, WARNING, ERROR

# 企业微信机器人配置
wechat:
  webhook_url: "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY"

# 系统监控配置
system:
  memory:
    enabled: true
    threshold: 80           # 内存使用率阈值 (%)
  disk:
    enabled: true
    threshold: 80           # 磁盘使用率阈值 (%)
    paths:                  # 要监控的磁盘路径，留空则只监控根目录
      - "/"
  cpu:
    enabled: true
    threshold: 80           # CPU 使用率阈值 (%)
    sample_interval: 1      # CPU 采样间隔（秒）
  swap:
    enabled: true
    threshold: 80           # Swap 使用率阈值 (%)

# 网络监控配置
network:
  traffic:
    enabled: true
    threshold_mbps: 100     # 流量阈值 (Mbps)
    sample_interval: 5      # 流量采样间隔（秒）
  connections:
    enabled: true
    threshold: 1000         # 连接数阈值

# Docker 监控配置
docker:
  enabled: true
  socket: "unix://var/run/docker.sock"  # Docker socket 路径
  containers:               # 要监控的容器列表
    - name: "nginx"
      check_health: true    # 是否检查健康状态
    - name: "mysql"
      check_health: true
    - name: "redis"
      check_health: false

# 定时状态报告配置
scheduled_report:
  enabled: true
  cron: "0 9 * * *"         # Cron 表达式，示例：每天早上 9 点
  # 常用 Cron 示例:
  # "0 9 * * *"     - 每天 9:00
  # "0 9,18 * * *"  - 每天 9:00 和 18:00
  # "0 */6 * * *"   - 每 6 小时
  # "0 9 * * 1"     - 每周一 9:00
  # "0 0 1 * *"     - 每月 1 号 0:00
```

---

## 消息格式设计

### 系统告警消息
```
⚠️ VPS 告警 [主机名]
━━━━━━━━━━━━━━━━
📊 内存使用率: 85.2% (阈值: 80%)
💾 磁盘使用率(/): 92.1% (阈值: 80%)
⏰ 时间: 2026-02-04 15:30:00
```

### Docker 告警消息
```
🐳 Docker 告警 [主机名]
━━━━━━━━━━━━━━━━
📦 容器: nginx
❌ 状态: exited (期望: running)
⏰ 时间: 2026-02-04 15:30:00
```

### 恢复消息
```
✅ VPS 恢复 [主机名]
━━━━━━━━━━━━━━━━
📊 内存使用率: 72.1% (已恢复正常)
⏰ 时间: 2026-02-04 15:45:00
```

### 定时状态报告
```
📊 VPS 状态报告 [主机名]
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
  • redis: ✅ running

⏰ 报告时间: 2026-02-04 09:00:00
```

---

## 安装部署流程

```bash
# 1. 创建项目目录
sudo mkdir -p /opt/vps-monitor
cd /opt/vps-monitor

# 2. 复制文件
sudo cp monitor.py config.yaml requirements.txt /opt/vps-monitor/

# 3. 安装依赖
sudo pip3 install -r requirements.txt

# 4. 修改配置文件
sudo vim config.yaml
# 填入企业微信 Webhook URL 和要监控的 Docker 容器

# 5. 安装 systemd 服务
sudo cp vps-monitor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable vps-monitor
sudo systemctl start vps-monitor

# 6. 查看状态
sudo systemctl status vps-monitor
```

---

## 风险与缓解

| 风险 | 缓解措施 |
|-----|---------|
| Docker 服务不可用 | 优雅降级，跳过 Docker 监控，记录警告日志 |
| 网络请求失败 | 重试机制，最多重试 3 次 |
| 配置文件错误 | 启动时验证配置，提供清晰错误提示 |
| 监控脚本崩溃 | systemd 自动重启，Restart=always |
| 磁盘空间不足 | 日志轮转，限制日志文件大小 |
| Cron 表达式无效 | 启动时验证 Cron 表达式，提供错误提示 |

---

## 下一步行动

1. **确认计划**: 请审阅此计划，提出修改意见
2. **开始实施**: 从 Phase 1.1 项目初始化开始
3. **迭代反馈**: 每个阶段完成后进行验证

---

**计划版本**: v1.1
**创建日期**: 2026-02-04
**更新日期**: 2026-02-04
**基于需求**: VPS 内存/磁盘/Docker 监控 + 企业微信告警 + 定时状态报告
