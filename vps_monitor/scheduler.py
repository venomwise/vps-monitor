"""Scheduled report module."""

import logging
from datetime import datetime
from typing import Optional

from .config import ConfigManager

try:
    from croniter import croniter
    CRONITER_AVAILABLE = True
except ImportError:
    croniter = None  # type: ignore
    CRONITER_AVAILABLE = False


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
