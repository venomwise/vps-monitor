"""Configuration manager for VPS monitor."""

import logging
import socket
from pathlib import Path
from typing import Any, Dict

import yaml

try:
    from croniter import croniter
    CRONITER_AVAILABLE = True
except ImportError:
    croniter = None  # type: ignore
    CRONITER_AVAILABLE = False


class ConfigManager:
    """配置管理器：加载和验证 YAML 配置文件"""

    DEFAULT_CONFIG = {
        'general': {
            'hostname': '',
            'check_interval': 900,
            'alert_cooldown': 300,
            'send_recovery': True,
            'log_level': 'INFO',
            'timezone': ''
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
