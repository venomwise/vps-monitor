"""System metrics collector."""

import logging
from typing import Dict, List, Optional

import psutil

from ..config import ConfigManager


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

    def check_thresholds(self) -> tuple[List[Dict], Dict[str, str]]:
        """检查阈值并返回告警列表和所有被检查的 key 及其当前值"""
        alerts = []
        checked_keys = {}
        data = self.collect_all()

        if 'memory' in data:
            key = 'system_memory'
            current_value = f"{data['memory']['percent']:.1f}%"
            checked_keys[key] = current_value
            threshold = self.config.get('system', 'memory', 'threshold', default=80)
            if data['memory']['percent'] > threshold:
                alerts.append({
                    'key': key,
                    'metric': '内存使用率',
                    'value': current_value,
                    'threshold': f"{threshold}%"
                })

        if 'swap' in data:
            key = 'system_swap'
            current_value = f"{data['swap']:.1f}%"
            checked_keys[key] = current_value
            threshold = self.config.get('system', 'swap', 'threshold', default=80)
            if data['swap'] > threshold:
                alerts.append({
                    'key': key,
                    'metric': 'Swap使用率',
                    'value': current_value,
                    'threshold': f"{threshold}%"
                })

        if 'disk' in data:
            threshold = self.config.get('system', 'disk', 'threshold', default=80)
            for path, disk_data in data['disk'].items():
                key = f'system_disk_{path}'
                current_value = f"{disk_data['percent']:.1f}%"
                checked_keys[key] = current_value
                if disk_data['percent'] > threshold:
                    alerts.append({
                        'key': key,
                        'metric': f'磁盘使用率({path})',
                        'value': current_value,
                        'threshold': f"{threshold}%"
                    })

        if 'cpu' in data:
            key = 'system_cpu'
            current_value = f"{data['cpu']:.1f}%"
            checked_keys[key] = current_value
            threshold = self.config.get('system', 'cpu', 'threshold', default=80)
            if data['cpu'] > threshold:
                alerts.append({
                    'key': key,
                    'metric': 'CPU使用率',
                    'value': current_value,
                    'threshold': f"{threshold}%"
                })

        return alerts, checked_keys
