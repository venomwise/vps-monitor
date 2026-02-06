"""Network metrics collector."""

import logging
import time
from typing import Dict, List

import psutil

from ..config import ConfigManager


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

    def check_thresholds(self) -> tuple[List[Dict], Dict[str, str]]:
        """检查阈值并返回告警列表和所有被检查的 key 及其当前值"""
        alerts = []
        checked_keys = {}
        data = self.collect_all()

        if 'traffic' in data:
            threshold = self.config.get('network', 'traffic', 'threshold_mbps', default=100)
            key_in = 'network_traffic_in'
            current_value_in = f"{data['traffic']['in_mbps']:.1f} Mbps"
            checked_keys[key_in] = current_value_in
            if data['traffic']['in_mbps'] > threshold:
                alerts.append({
                    'key': key_in,
                    'metric': '入站流量',
                    'value': current_value_in,
                    'threshold': f"{threshold} Mbps"
                })

            key_out = 'network_traffic_out'
            current_value_out = f"{data['traffic']['out_mbps']:.1f} Mbps"
            checked_keys[key_out] = current_value_out
            if data['traffic']['out_mbps'] > threshold:
                alerts.append({
                    'key': key_out,
                    'metric': '出站流量',
                    'value': current_value_out,
                    'threshold': f"{threshold} Mbps"
                })

        if 'connections' in data and data['connections'] >= 0:
            key = 'network_connections'
            current_value = str(data['connections'])
            checked_keys[key] = current_value
            threshold = self.config.get('network', 'connections', 'threshold', default=1000)
            if data['connections'] > threshold:
                alerts.append({
                    'key': key,
                    'metric': '网络连接数',
                    'value': current_value,
                    'threshold': str(threshold)
                })

        return alerts, checked_keys
