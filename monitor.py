#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VPS 监控系统
实时监控系统资源和 Docker 容器状态，通过企业微信机器人发送告警通知
"""

import os
import sys
import json
import time
import signal
import socket
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

import yaml
import psutil
import requests

try:
    import docker
    DOCKER_AVAILABLE = True
except ImportError:
    DOCKER_AVAILABLE = False

try:
    from croniter import croniter
    CRONITER_AVAILABLE = True
except ImportError:
    croniter = None  # type: ignore
    CRONITER_AVAILABLE = False


# ============================================================================
# 配置管理模块
# ============================================================================

class ConfigManager:
    """配置管理器：加载和验证 YAML 配置文件"""

    DEFAULT_CONFIG = {
        'general': {
            'hostname': '',
            'check_interval': 900,
            'alert_cooldown': 300,
            'send_recovery': True,
            'log_level': 'INFO'
        },
        'wechat': {
            'webhook_url': ''
        },
        'system': {
            'memory': {'enabled': True, 'threshold': 80},
            'disk': {'enabled': True, 'threshold': 80, 'paths': ['/']},
            'cpu': {'enabled': True, 'threshold': 80, 'sample_interval': 1},
            'swap': {'enabled': True, 'threshold': 80}
        },
        'network': {
            'traffic': {'enabled': True, 'threshold_mbps': 100, 'sample_interval': 5},
            'connections': {'enabled': True, 'threshold': 1000}
        },
        'docker': {
            'enabled': True,
            'socket': 'unix://var/run/docker.sock',
            'containers': []
        },
        'scheduled_report': {
            'enabled': True,
            'cron': '0 9 * * *'
        }
    }

    def __init__(self, config_path: str):
        self.config_path = Path(config_path)
        self.config = {}
        self.load()

    def load(self) -> Dict:
        """加载配置文件"""
        if not self.config_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {self.config_path}")

        with open(self.config_path, 'r', encoding='utf-8') as f:
            user_config = yaml.safe_load(f) or {}

        self.config = self._merge_config(self.DEFAULT_CONFIG, user_config)
        self._validate()
        return self.config

    def _merge_config(self, default: Dict, user: Dict) -> Dict:
        """递归合并配置"""
        result = default.copy()
        for key, value in user.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_config(result[key], value)
            else:
                result[key] = value
        return result

    def _validate(self):
        """验证配置"""
        webhook_url = self.config.get('wechat', {}).get('webhook_url', '')
        if not webhook_url or webhook_url == 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY':
            logging.warning("企业微信 Webhook URL 未配置，通知功能将不可用")

        if CRONITER_AVAILABLE and croniter is not None and self.config.get('scheduled_report', {}).get('enabled'):
            cron_expr = self.config['scheduled_report'].get('cron', '')
            if cron_expr:
                try:
                    croniter(cron_expr)
                except (KeyError, ValueError) as e:
                    raise ValueError(f"无效的 Cron 表达式 '{cron_expr}': {e}")

    def get(self, *keys: str, default: Any = None) -> Any:
        """获取配置项"""
        value: Any = self.config
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key, default)
            else:
                return default
        return value

    @property
    def hostname(self) -> str:
        """获取主机名"""
        name = self.get('general', 'hostname')
        return str(name) if name else socket.gethostname()


# ============================================================================
# 企业微信通知模块
# ============================================================================

class WeChatNotifier:
    """企业微信机器人通知器"""

    def __init__(self, webhook_url: str, max_retries: int = 3):
        self.webhook_url = webhook_url
        self.max_retries = max_retries
        self.enabled = bool(webhook_url and 'YOUR_KEY' not in webhook_url)

    def send(self, content: str, msg_type: str = 'markdown') -> bool:
        """发送消息到企业微信"""
        if not self.enabled:
            logging.debug("企业微信通知未启用，跳过发送")
            return False

        payload = {
            'msgtype': msg_type,
            msg_type: {'content': content}
        }

        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    self.webhook_url,
                    json=payload,
                    timeout=10
                )
                result = response.json()
                if result.get('errcode') == 0:
                    logging.info("消息发送成功")
                    return True
                else:
                    logging.error(f"消息发送失败: {result.get('errmsg')}")
            except requests.RequestException as e:
                logging.error(f"请求失败 (尝试 {attempt + 1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)

        return False

    def send_alert(self, hostname: str, alerts: List[Dict]) -> bool:
        """发送告警消息"""
        if not alerts:
            return False

        lines = [
            f"### <font color=\"warning\">VPS 告警</font> [{hostname}]",
            ""
        ]
        for alert in alerts:
            lines.append(f"> **{alert['metric']}**: <font color=\"warning\">{alert['value']}</font>")
            lines.append(f"> 阈值: <font color=\"comment\">{alert['threshold']}</font>")
            lines.append("")
        lines.append(f"**时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        return self.send('\n'.join(lines))

    def send_docker_alert(self, hostname: str, container: str, status: str, expected: str = 'running') -> bool:
        """发送 Docker 告警消息"""
        content = f"""### <font color="warning">Docker 告警</font> [{hostname}]

> **容器**: `{container}`
> **状态**: <font color="warning">{status}</font>
> **期望**: <font color="comment">{expected}</font>

**时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
        return self.send(content)

    def send_recovery(self, hostname: str, metric: str, value: str) -> bool:
        """发送恢复消息"""
        content = f"""### <font color="info">VPS 恢复</font> [{hostname}]

> **{metric}**: <font color="info">{value}</font>

**时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
        return self.send(content)

    def send_docker_recovery(self, hostname: str, container: str, status: str) -> bool:
        """发送 Docker 恢复消息"""
        content = f"""### <font color="info">Docker 恢复</font> [{hostname}]

> **容器**: `{container}`
> **状态**: <font color="info">{status}</font>

**时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
        return self.send(content)

    def send_status_report(self, hostname: str, report: Dict) -> bool:
        """发送定时状态报告"""
        lines = [f"### VPS 状态报告 [{hostname}]", ""]

        # 系统状态
        if 'system' in report:
            sys_info = report['system']
            lines.append("#### 系统状态")
            if 'cpu' in sys_info:
                lines.append(f"> CPU: **{sys_info['cpu']:.1f}%**")
            if 'memory' in sys_info:
                mem = sys_info['memory']
                lines.append(f"> 内存: **{mem['percent']:.1f}%** ({mem['used']:.1f}GB / {mem['total']:.1f}GB)")
            if 'swap' in sys_info:
                lines.append(f"> Swap: **{sys_info['swap']:.1f}%**")
            if 'disk' in sys_info:
                for path, disk in sys_info['disk'].items():
                    lines.append(f"> 磁盘`{path}`: **{disk['percent']:.1f}%** ({disk['used']:.1f}GB / {disk['total']:.1f}GB)")

        # 网络状态
        if 'network' in report:
            net_info = report['network']
            lines.append("")
            lines.append("#### 网络状态")
            if 'traffic' in net_info:
                lines.append(f"> 入站: **{net_info['traffic']['in_mbps']:.1f} Mbps**")
                lines.append(f"> 出站: **{net_info['traffic']['out_mbps']:.1f} Mbps**")
            if 'connections' in net_info:
                lines.append(f"> 连接数: **{net_info['connections']}**")

        # Docker 状态
        if 'docker' in report and report['docker']:
            lines.append("")
            lines.append("#### Docker 容器")
            for container in report['docker']:
                if container['status'] == 'running':
                    status_text = f"<font color=\"info\">{container['status']}</font>"
                else:
                    status_text = f"<font color=\"warning\">{container['status']}</font>"
                health_str = f" ({container['health']})" if container.get('health') else ""
                lines.append(f"> `{container['name']}`: {status_text}{health_str}")

        lines.append("")
        lines.append(f"**报告时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        return self.send('\n'.join(lines))


# ============================================================================
# 告警状态管理模块
# ============================================================================

class AlertStateManager:
    """告警状态管理器：处理告警去重和冷却"""

    def __init__(self, state_file: str, cooldown: int = 300):
        self.state_file = Path(state_file)
        self.cooldown = cooldown
        self.state = self._load_state()

    def _load_state(self) -> Dict:
        """加载告警状态"""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                logging.warning("告警状态文件损坏，重新创建")
        return {'alerts': {}}

    def _save_state(self):
        """保存告警状态"""
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(self.state, f, indent=2, ensure_ascii=False)
        except IOError as e:
            logging.error(f"保存告警状态失败: {e}")

    def should_alert(self, alert_key: str) -> bool:
        """检查是否应该发送告警（冷却检查）"""
        now = time.time()
        last_alert = self.state['alerts'].get(alert_key, {}).get('last_alert', 0)
        return (now - last_alert) >= self.cooldown

    def record_alert(self, alert_key: str):
        """记录告警"""
        self.state['alerts'][alert_key] = {
            'last_alert': time.time(),
            'active': True
        }
        self._save_state()

    def is_active(self, alert_key: str) -> bool:
        """检查告警是否处于活跃状态"""
        return self.state['alerts'].get(alert_key, {}).get('active', False)

    def clear_alert(self, alert_key: str):
        """清除告警状态"""
        if alert_key in self.state['alerts']:
            self.state['alerts'][alert_key]['active'] = False
            self._save_state()

    def get_active_alerts(self) -> List[str]:
        """获取所有活跃告警"""
        return [k for k, v in self.state['alerts'].items() if v.get('active')]


# ============================================================================
# 系统监控采集器
# ============================================================================

class SystemCollector:
    """系统资源采集器"""

    def __init__(self, config: ConfigManager):
        self.config = config

    def collect_memory(self) -> Dict:
        """采集内存使用率"""
        mem = psutil.virtual_memory()
        return {
            'percent': mem.percent,
            'used': mem.used / (1024 ** 3),
            'total': mem.total / (1024 ** 3),
            'available': mem.available / (1024 ** 3)
        }

    def collect_swap(self) -> Dict:
        """采集 Swap 使用率"""
        swap = psutil.swap_memory()
        return {
            'percent': swap.percent,
            'used': swap.used / (1024 ** 3),
            'total': swap.total / (1024 ** 3)
        }

    def collect_disk(self, paths: Optional[List[str]] = None) -> Dict[str, Dict]:
        """采集磁盘使用率"""
        if paths is None:
            disk_paths = self.config.get('system', 'disk', 'paths', default=['/'])
            paths = disk_paths if isinstance(disk_paths, list) else ['/']

        result = {}
        for path in paths:
            try:
                usage = psutil.disk_usage(path)
                result[path] = {
                    'percent': usage.percent,
                    'used': usage.used / (1024 ** 3),
                    'total': usage.total / (1024 ** 3),
                    'free': usage.free / (1024 ** 3)
                }
            except (FileNotFoundError, PermissionError) as e:
                logging.warning(f"无法获取磁盘 {path} 信息: {e}")
        return result

    def collect_cpu(self, interval: Optional[float] = None) -> float:
        """采集 CPU 使用率"""
        if interval is None:
            cfg_interval = self.config.get('system', 'cpu', 'sample_interval', default=1)
            interval = float(cfg_interval) if isinstance(cfg_interval, (int, float, str)) else 1.0
        return psutil.cpu_percent(interval=interval)

    def collect_all(self) -> Dict:
        """采集所有系统指标"""
        result = {}

        if self.config.get('system', 'memory', 'enabled', default=True):
            result['memory'] = self.collect_memory()

        if self.config.get('system', 'swap', 'enabled', default=True):
            result['swap'] = self.collect_swap()['percent']

        if self.config.get('system', 'disk', 'enabled', default=True):
            result['disk'] = self.collect_disk()

        if self.config.get('system', 'cpu', 'enabled', default=True):
            result['cpu'] = self.collect_cpu()

        return result

    def check_thresholds(self) -> List[Dict]:
        """检查阈值并返回告警列表"""
        alerts = []
        data = self.collect_all()

        # 内存检查
        if 'memory' in data:
            threshold = self.config.get('system', 'memory', 'threshold', default=80)
            if data['memory']['percent'] > threshold:
                alerts.append({
                    'key': 'system_memory',
                    'metric': '内存使用率',
                    'value': f"{data['memory']['percent']:.1f}%",
                    'threshold': f"{threshold}%"
                })

        # Swap 检查
        if 'swap' in data:
            threshold = self.config.get('system', 'swap', 'threshold', default=80)
            if data['swap'] > threshold:
                alerts.append({
                    'key': 'system_swap',
                    'metric': 'Swap使用率',
                    'value': f"{data['swap']:.1f}%",
                    'threshold': f"{threshold}%"
                })

        # 磁盘检查
        if 'disk' in data:
            threshold = self.config.get('system', 'disk', 'threshold', default=80)
            for path, disk_data in data['disk'].items():
                if disk_data['percent'] > threshold:
                    alerts.append({
                        'key': f'system_disk_{path}',
                        'metric': f'磁盘使用率({path})',
                        'value': f"{disk_data['percent']:.1f}%",
                        'threshold': f"{threshold}%"
                    })

        # CPU 检查
        if 'cpu' in data:
            threshold = self.config.get('system', 'cpu', 'threshold', default=80)
            if data['cpu'] > threshold:
                alerts.append({
                    'key': 'system_cpu',
                    'metric': 'CPU使用率',
                    'value': f"{data['cpu']:.1f}%",
                    'threshold': f"{threshold}%"
                })

        return alerts


# ============================================================================
# 网络监控采集器
# ============================================================================

class NetworkCollector:
    """网络监控采集器"""

    def __init__(self, config: ConfigManager):
        self.config = config
        self._last_net_io = None
        self._last_net_time = None

    def collect_traffic(self) -> Dict:
        """采集网络流量（需要两次采样计算速率）"""
        current_io = psutil.net_io_counters()
        current_time = time.time()

        result = {
            'bytes_sent': current_io.bytes_sent,
            'bytes_recv': current_io.bytes_recv,
            'in_mbps': 0.0,
            'out_mbps': 0.0
        }

        if self._last_net_io is not None and self._last_net_time is not None:
            time_delta = current_time - self._last_net_time
            if time_delta > 0:
                bytes_recv_delta = current_io.bytes_recv - self._last_net_io.bytes_recv
                bytes_sent_delta = current_io.bytes_sent - self._last_net_io.bytes_sent
                result['in_mbps'] = (bytes_recv_delta * 8) / (time_delta * 1_000_000)
                result['out_mbps'] = (bytes_sent_delta * 8) / (time_delta * 1_000_000)

        self._last_net_io = current_io
        self._last_net_time = current_time

        return result

    def collect_connections(self) -> int:
        """采集网络连接数"""
        try:
            connections = psutil.net_connections(kind='inet')
            return len(connections)
        except (psutil.AccessDenied, PermissionError):
            logging.warning("无权限获取网络连接数，需要 root 权限")
            return -1

    def collect_all(self) -> Dict:
        """采集所有网络指标"""
        result = {}

        if self.config.get('network', 'traffic', 'enabled', default=True):
            result['traffic'] = self.collect_traffic()

        if self.config.get('network', 'connections', 'enabled', default=True):
            result['connections'] = self.collect_connections()

        return result

    def check_thresholds(self) -> List[Dict]:
        """检查阈值并返回告警列表"""
        alerts = []
        data = self.collect_all()

        # 流量检查
        if 'traffic' in data:
            threshold = self.config.get('network', 'traffic', 'threshold_mbps', default=100)
            if data['traffic']['in_mbps'] > threshold:
                alerts.append({
                    'key': 'network_traffic_in',
                    'metric': '入站流量',
                    'value': f"{data['traffic']['in_mbps']:.1f} Mbps",
                    'threshold': f"{threshold} Mbps"
                })
            if data['traffic']['out_mbps'] > threshold:
                alerts.append({
                    'key': 'network_traffic_out',
                    'metric': '出站流量',
                    'value': f"{data['traffic']['out_mbps']:.1f} Mbps",
                    'threshold': f"{threshold} Mbps"
                })

        # 连接数检查
        if 'connections' in data and data['connections'] >= 0:
            threshold = self.config.get('network', 'connections', 'threshold', default=1000)
            if data['connections'] > threshold:
                alerts.append({
                    'key': 'network_connections',
                    'metric': '网络连接数',
                    'value': str(data['connections']),
                    'threshold': str(threshold)
                })

        return alerts


# ============================================================================
# Docker 监控采集器
# ============================================================================

class DockerCollector:
    """Docker 容器监控采集器"""

    def __init__(self, config: ConfigManager):
        self.config = config
        self.client = None
        self.available = False
        self._init_client()

    def _init_client(self):
        """初始化 Docker 客户端"""
        if not DOCKER_AVAILABLE:
            logging.warning("docker 库未安装，Docker 监控不可用")
            return

        if not self.config.get('docker', 'enabled', default=True):
            logging.info("Docker 监控已禁用")
            return

        try:
            socket_path = self.config.get('docker', 'socket', default='unix://var/run/docker.sock')
            self.client = docker.DockerClient(base_url=socket_path)
            self.client.ping()
            self.available = True
            logging.info("Docker 客户端初始化成功")
        except Exception as e:
            logging.warning(f"Docker 客户端初始化失败: {e}")
            self.available = False

    def get_container_status(self, container_name: str) -> Optional[Dict]:
        """获取指定容器的状态"""
        if not self.available or self.client is None:
            return None

        try:
            container = self.client.containers.get(container_name)
            status = {
                'name': container_name,
                'status': container.status,
                'health': None
            }

            # 检查健康状态
            if container.attrs.get('State', {}).get('Health'):
                status['health'] = container.attrs['State']['Health'].get('Status')

            return status
        except Exception as e:
            if 'NotFound' in type(e).__name__ or '404' in str(e):
                return {'name': container_name, 'status': 'not_found', 'health': None}
            logging.error(f"获取容器 {container_name} 状态失败: {e}")
            return None

    def collect_all(self) -> List[Dict]:
        """采集所有配置的容器状态"""
        if not self.available:
            return []

        containers_config = self.config.get('docker', 'containers', default=[])
        if not isinstance(containers_config, list):
            return []
        results = []

        for container_cfg in containers_config:
            name = container_cfg.get('name') if isinstance(container_cfg, dict) else container_cfg
            if not isinstance(name, str):
                continue
            status = self.get_container_status(name)
            if status:
                results.append(status)

        return results

    def check_containers(self) -> List[Dict]:
        """检查容器状态并返回告警列表"""
        if not self.available:
            return []

        alerts = []
        containers_config = self.config.get('docker', 'containers', default=[])
        if not isinstance(containers_config, list):
            return []

        for container_cfg in containers_config:
            if isinstance(container_cfg, dict):
                name = container_cfg.get('name')
                check_health = container_cfg.get('check_health', False)
            else:
                name = container_cfg
                check_health = False

            if not isinstance(name, str):
                continue
            status = self.get_container_status(name)
            if not status:
                continue

            # 检查运行状态
            if status['status'] != 'running':
                alerts.append({
                    'key': f'docker_{name}_status',
                    'container': name,
                    'type': 'status',
                    'current': status['status'],
                    'expected': 'running'
                })

            # 检查健康状态
            if check_health and status['health'] and status['health'] != 'healthy':
                alerts.append({
                    'key': f'docker_{name}_health',
                    'container': name,
                    'type': 'health',
                    'current': status['health'],
                    'expected': 'healthy'
                })

        return alerts


# ============================================================================
# 定时报告模块
# ============================================================================

class ScheduledReporter:
    """定时状态报告器"""

    def __init__(self, config: ConfigManager):
        self.config = config
        self.enabled = config.get('scheduled_report', 'enabled', default=False)
        cron_cfg = config.get('scheduled_report', 'cron', default='0 9 * * *')
        self.cron_expr = str(cron_cfg) if cron_cfg else '0 9 * * *'
        self._next_run: Optional[datetime] = None
        self._init_schedule()

    def _init_schedule(self):
        """初始化定时计划"""
        if not self.enabled:
            return

        if not CRONITER_AVAILABLE:
            logging.warning("croniter 库未安装，定时报告功能不可用")
            self.enabled = False
            return

        if croniter is None:
            return

        try:
            cron = croniter(self.cron_expr, datetime.now())
            self._next_run = cron.get_next(datetime)
            logging.info(f"定时报告已启用，下次执行时间: {self._next_run}")
        except Exception as e:
            logging.error(f"Cron 表达式解析失败: {e}")
            self.enabled = False

    def should_run(self) -> bool:
        """检查是否应该执行定时报告"""
        if not self.enabled or self._next_run is None:
            return False

        return datetime.now() >= self._next_run

    def update_next_run(self):
        """更新下次执行时间"""
        if not self.enabled or croniter is None:
            return

        try:
            cron = croniter(self.cron_expr, datetime.now())
            self._next_run = cron.get_next(datetime)
            logging.info(f"下次定时报告时间: {self._next_run}")
        except Exception as e:
            logging.error(f"更新下次执行时间失败: {e}")


# ============================================================================
# 主监控程序
# ============================================================================

class VPSMonitor:
    """VPS 监控主程序"""

    def __init__(self, config_path: str):
        self.config_path = config_path
        self.running = False
        self._setup_logging()
        self._init_components()

    def _setup_logging(self):
        """设置日志"""
        script_dir = Path(__file__).parent
        log_dir = script_dir / 'logs'
        log_dir.mkdir(exist_ok=True)

        log_file = log_dir / 'monitor.log'

        # 临时加载配置获取日志级别
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}
            log_level = config.get('general', {}).get('log_level', 'INFO')
        except Exception:
            log_level = 'INFO'

        logging.basicConfig(
            level=getattr(logging, log_level.upper(), logging.INFO),
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler()
            ]
        )

    def _init_components(self):
        """初始化所有组件"""
        self.config = ConfigManager(self.config_path)

        # 初始化通知器
        webhook_url_cfg = self.config.get('wechat', 'webhook_url', default='')
        webhook_url = str(webhook_url_cfg) if webhook_url_cfg else ''
        self.notifier = WeChatNotifier(webhook_url)

        # 初始化告警状态管理器
        script_dir = Path(__file__).parent
        state_file = script_dir / 'alert_state.json'
        cooldown_cfg = self.config.get('general', 'alert_cooldown', default=300)
        cooldown = int(cooldown_cfg) if isinstance(cooldown_cfg, (int, float, str)) else 300
        self.alert_manager = AlertStateManager(str(state_file), cooldown)

        # 初始化采集器
        self.system_collector = SystemCollector(self.config)
        self.network_collector = NetworkCollector(self.config)
        self.docker_collector = DockerCollector(self.config)

        # 初始化定时报告器
        self.scheduled_reporter = ScheduledReporter(self.config)

        logging.info("VPS 监控系统初始化完成")

    def _setup_signal_handlers(self):
        """设置信号处理"""
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """信号处理函数"""
        logging.info(f"收到信号 {signum}，正在停止监控...")
        self.running = False

    def collect_status_report(self) -> Dict:
        """收集完整状态报告"""
        report = {}

        # 系统状态
        report['system'] = self.system_collector.collect_all()

        # 网络状态
        report['network'] = self.network_collector.collect_all()

        # Docker 状态
        report['docker'] = self.docker_collector.collect_all()

        return report

    def _process_system_alerts(self, alerts: List[Dict]):
        """处理系统告警"""
        hostname = self.config.hostname
        send_recovery = self.config.get('general', 'send_recovery', default=True)

        # 获取当前告警的 key 集合
        current_alert_keys = {a['key'] for a in alerts}

        # 检查恢复
        if send_recovery:
            for active_key in self.alert_manager.get_active_alerts():
                if active_key.startswith('system_') and active_key not in current_alert_keys:
                    self.notifier.send_recovery(hostname, active_key, "已恢复正常")
                    self.alert_manager.clear_alert(active_key)

        # 发送新告警
        alerts_to_send = []
        for alert in alerts:
            if self.alert_manager.should_alert(alert['key']):
                alerts_to_send.append(alert)
                self.alert_manager.record_alert(alert['key'])

        if alerts_to_send:
            self.notifier.send_alert(hostname, alerts_to_send)

    def _process_docker_alerts(self, alerts: List[Dict]):
        """处理 Docker 告警"""
        hostname = self.config.hostname
        send_recovery = self.config.get('general', 'send_recovery', default=True)

        # 获取当前告警的 key 集合
        current_alert_keys = {a['key'] for a in alerts}

        # 检查恢复
        if send_recovery:
            for active_key in self.alert_manager.get_active_alerts():
                if active_key.startswith('docker_') and active_key not in current_alert_keys:
                    container_name = active_key.replace('docker_', '').rsplit('_', 1)[0]
                    self.notifier.send_docker_recovery(hostname, container_name, 'running')
                    self.alert_manager.clear_alert(active_key)

        # 发送新告警
        for alert in alerts:
            if self.alert_manager.should_alert(alert['key']):
                self.notifier.send_docker_alert(
                    hostname,
                    alert['container'],
                    alert['current'],
                    alert['expected']
                )
                self.alert_manager.record_alert(alert['key'])

    def run_once(self):
        """执行一次监控检查"""
        logging.debug("开始监控检查...")

        # 系统监控
        system_alerts = self.system_collector.check_thresholds()
        self._process_system_alerts(system_alerts)

        # 网络监控
        network_alerts = self.network_collector.check_thresholds()
        self._process_system_alerts(network_alerts)

        # Docker 监控
        docker_alerts = self.docker_collector.check_containers()
        self._process_docker_alerts(docker_alerts)

        # 定时报告
        if self.scheduled_reporter.should_run():
            logging.info("执行定时状态报告...")
            report = self.collect_status_report()
            self.notifier.send_status_report(self.config.hostname, report)
            self.scheduled_reporter.update_next_run()

        logging.debug("监控检查完成")

    def run(self):
        """运行监控循环"""
        self._setup_signal_handlers()
        self.running = True

        check_interval_cfg = self.config.get('general', 'check_interval', default=900)
        check_interval = int(check_interval_cfg) if isinstance(check_interval_cfg, (int, float, str)) else 900
        logging.info(f"VPS 监控已启动，检查间隔: {check_interval} 秒")

        # 首次运行网络采集以初始化基准值
        self.network_collector.collect_traffic()

        while self.running:
            try:
                self.run_once()
            except Exception as e:
                logging.error(f"监控检查出错: {e}", exc_info=True)

            # 等待下次检查
            for _ in range(check_interval):
                if not self.running:
                    break
                time.sleep(1)

        logging.info("VPS 监控已停止")


# ============================================================================
# 入口点
# ============================================================================

def main():
    """主函数"""
    script_dir = Path(__file__).parent
    config_path = script_dir / 'config.yaml'

    if not config_path.exists():
        print(f"错误: 配置文件不存在: {config_path}")
        sys.exit(1)

    try:
        monitor = VPSMonitor(str(config_path))
        monitor.run()
    except KeyboardInterrupt:
        print("\n监控已停止")
    except Exception as e:
        print(f"错误: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
