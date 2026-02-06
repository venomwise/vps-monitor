"""Alert state persistence module."""

import json
import logging
import time
from pathlib import Path
from typing import Dict, List


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
