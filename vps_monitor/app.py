"""Application orchestrator for VPS monitor."""

import logging
import signal
import time
from pathlib import Path
from typing import Dict, List

import yaml

from .collectors import DockerCollector, NetworkCollector, SystemCollector
from .config import ConfigManager
from .notifier import WeChatNotifier
from .scheduler import ScheduledReporter
from .state import AlertStateManager


class VPSMonitor:
    """VPS 监控主程序"""

    def __init__(self, config_path: str):
        self.config_path = config_path
        self.base_dir = Path(config_path).resolve().parent
        self.running = False
        self._setup_logging()
        self._init_components()

    def _setup_logging(self):
        """设置日志"""
        log_dir = self.base_dir / 'logs'
        log_dir.mkdir(exist_ok=True)

        log_file = log_dir / 'monitor.log'

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}
            log_level = config.get('general', {}).get('log_level', 'INFO')
        except Exception:
            log_level = 'INFO'

        logging.basicConfig(
            level=getattr(logging, str(log_level).upper(), logging.INFO),
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler()
            ]
        )

    def _init_components(self):
        """初始化所有组件"""
        self.config = ConfigManager(self.config_path)

        webhook_url_cfg = self.config.get('wechat', 'webhook_url', default='')
        webhook_url = str(webhook_url_cfg) if webhook_url_cfg else ''
        timezone_cfg = self.config.get('general', 'timezone', default='')
        timezone_str = str(timezone_cfg) if timezone_cfg else ''
        self.notifier = WeChatNotifier(webhook_url, timezone_str=timezone_str)

        state_file = self.base_dir / 'alert_state.json'
        cooldown_cfg = self.config.get('general', 'alert_cooldown', default=300)
        cooldown = int(cooldown_cfg) if isinstance(cooldown_cfg, (int, float, str)) else 300
        self.alert_manager = AlertStateManager(str(state_file), cooldown)

        self.system_collector = SystemCollector(self.config)
        self.network_collector = NetworkCollector(self.config)
        self.docker_collector = DockerCollector(self.config)

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
        report['system'] = self.system_collector.collect_all()
        report['network'] = self.network_collector.collect_all()
        report['docker'] = self.docker_collector.collect_all()
        return report

    def _process_system_alerts(self, alerts: List[Dict], checked_keys: Dict[str, str]):
        """处理系统告警"""
        hostname = self.config.hostname
        send_recovery = self.config.get('general', 'send_recovery', default=True)

        current_alert_keys = {a['key'] for a in alerts}

        alerts_to_send = []
        for alert in alerts:
            if self.alert_manager.should_alert(alert['key']):
                alerts_to_send.append(alert)
                self.alert_manager.record_alert(alert['key'])

        if alerts_to_send:
            self.notifier.send_alert(hostname, alerts_to_send)

        if send_recovery:
            for active_key in self.alert_manager.get_active_alerts():
                if (active_key.startswith('system_') or active_key.startswith('network_')):
                    if active_key in checked_keys and active_key not in current_alert_keys:
                        metric_name = self._get_metric_display_name(active_key)
                        current_value = checked_keys[active_key]
                        self.notifier.send_recovery(hostname, metric_name, current_value)
                        self.alert_manager.clear_alert(active_key)

    def _get_metric_display_name(self, alert_key: str) -> str:
        """将告警 key 转换为友好的显示名称"""
        key_mapping = {
            'system_memory': '内存使用率',
            'system_swap': 'Swap使用率',
            'system_cpu': 'CPU使用率',
            'network_traffic_in': '入站流量',
            'network_traffic_out': '出站流量',
            'network_connections': '网络连接数',
        }
        if alert_key in key_mapping:
            return key_mapping[alert_key]
        if alert_key.startswith('system_disk_'):
            path = alert_key[len('system_disk_'):]
            return f'磁盘使用率({path})'
        return alert_key

    def _process_docker_alerts(self, alerts: List[Dict]):
        """处理 Docker 告警"""
        hostname = self.config.hostname
        send_recovery = self.config.get('general', 'send_recovery', default=True)

        current_alert_keys = {a['key'] for a in alerts}

        if send_recovery:
            for active_key in self.alert_manager.get_active_alerts():
                if active_key.startswith('docker_') and active_key not in current_alert_keys:
                    container_name = active_key.replace('docker_', '').rsplit('_', 1)[0]
                    self.notifier.send_docker_recovery(hostname, container_name, 'running')
                    self.alert_manager.clear_alert(active_key)

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

        system_alerts, system_checked_keys = self.system_collector.check_thresholds()
        network_alerts, network_checked_keys = self.network_collector.check_thresholds()

        all_alerts = system_alerts + network_alerts
        all_checked_keys = {**system_checked_keys, **network_checked_keys}
        self._process_system_alerts(all_alerts, all_checked_keys)

        docker_alerts = self.docker_collector.check_containers()
        self._process_docker_alerts(docker_alerts)

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

        self.network_collector.collect_traffic()

        while self.running:
            try:
                self.run_once()
            except Exception as e:
                logging.error(f"监控检查出错: {e}", exc_info=True)

            for _ in range(check_interval):
                if not self.running:
                    break
                time.sleep(1)

        logging.info("VPS 监控已停止")
