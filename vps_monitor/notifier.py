"""Notification module for WeChat bot."""

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import requests


class WeChatNotifier:
    """企业微信机器人通知器"""

    def __init__(self, webhook_url: str, max_retries: int = 3, timezone_str: str = ''):
        self.webhook_url = webhook_url
        self.max_retries = max_retries
        self.enabled = bool(webhook_url and 'YOUR_KEY' not in webhook_url)
        self._tz = self._parse_timezone(timezone_str)

    def _parse_timezone(self, tz_str: str) -> Optional[timezone]:
        """解析时区配置"""
        if not tz_str:
            return None
        tz_str = tz_str.strip().upper()
        if tz_str.startswith('UTC'):
            offset_str = tz_str[3:]
            if offset_str:
                try:
                    if ':' in offset_str:
                        parts = offset_str.split(':')
                        hours = int(parts[0])
                        minutes = int(parts[1]) if len(parts) > 1 else 0
                    else:
                        hours = int(offset_str)
                        minutes = 0
                    return timezone(timedelta(hours=hours, minutes=minutes))
                except ValueError:
                    logging.warning(f"无效的时区格式: {tz_str}，使用系统时区")
                    return None
            return timezone.utc

        tz_aliases = {
            'CST': timezone(timedelta(hours=8)),
            'JST': timezone(timedelta(hours=9)),
            'KST': timezone(timedelta(hours=9)),
            'EST': timezone(timedelta(hours=-5)),
            'PST': timezone(timedelta(hours=-8)),
        }
        if tz_str in tz_aliases:
            return tz_aliases[tz_str]
        logging.warning(f"未知的时区: {tz_str}，使用系统时区")
        return None

    def _get_current_time(self) -> str:
        """获取当前时间字符串（考虑时区配置）"""
        if self._tz:
            return datetime.now(self._tz).strftime('%Y-%m-%d %H:%M:%S')
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

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
            f"⚠️ VPS 告警 [{hostname}]",
            "━━━━━━━━━━━━━━━━"
        ]
        for alert in alerts:
            lines.append(f"📊 {alert['metric']}: {alert['value']} (阈值: {alert['threshold']})")
        lines.append(f"⏰ 时间: {self._get_current_time()}")

        return self.send('\n'.join(lines), msg_type='text')

    def send_docker_alert(self, hostname: str, container: str, status: str, expected: str = 'running') -> bool:
        """发送 Docker 告警消息"""
        content = f"""🐳 Docker 告警 [{hostname}]
━━━━━━━━━━━━━━━━
📦 容器: {container}
❌ 状态: {status} (期望: {expected})
⏰ 时间: {self._get_current_time()}"""
        return self.send(content, msg_type='text')

    def send_recovery(self, hostname: str, metric: str, value: str) -> bool:
        """发送恢复消息"""
        content = f"""✅ VPS 恢复 [{hostname}]
━━━━━━━━━━━━━━━━
📊 {metric}: {value} (已恢复正常)
⏰ 时间: {self._get_current_time()}"""
        return self.send(content, msg_type='text')

    def send_docker_recovery(self, hostname: str, container: str, status: str) -> bool:
        """发送 Docker 恢复消息"""
        content = f"""✅ Docker 恢复 [{hostname}]
━━━━━━━━━━━━━━━━
📦 容器: {container}
✅ 状态: {status} (已恢复正常)
⏰ 时间: {self._get_current_time()}"""
        return self.send(content, msg_type='text')

    def send_status_report(self, hostname: str, report: Dict) -> bool:
        """发送定时状态报告"""
        lines = [f"📊 VPS 状态报告 [{hostname}]", "━━━━━━━━━━━━━━━━━━━━━━"]

        if 'system' in report:
            sys_info = report['system']
            lines.append("🖥️ 系统状态")
            if 'cpu' in sys_info:
                lines.append(f"  • CPU: {sys_info['cpu']:.1f}%")
            if 'memory' in sys_info:
                mem = sys_info['memory']
                lines.append(f"  • 内存: {mem['percent']:.1f}% ({mem['used']:.1f}GB / {mem['total']:.1f}GB)")
            if 'swap' in sys_info:
                lines.append(f"  • Swap: {sys_info['swap']:.1f}%")
            if 'disk' in sys_info:
                for path, disk in sys_info['disk'].items():
                    lines.append(f"  • 磁盘({path}): {disk['percent']:.1f}% ({disk['used']:.1f}GB / {disk['total']:.1f}GB)")

        if 'network' in report:
            net_info = report['network']
            lines.append("")
            lines.append("🌐 网络状态")
            if 'traffic' in net_info:
                lines.append(f"  • 入站: {net_info['traffic']['in_mbps']:.1f} Mbps")
                lines.append(f"  • 出站: {net_info['traffic']['out_mbps']:.1f} Mbps")
            if 'connections' in net_info:
                lines.append(f"  • 连接数: {net_info['connections']}")

        if 'docker' in report and report['docker']:
            lines.append("")
            lines.append("🐳 Docker 容器")
            for container in report['docker']:
                status_icon = "✅" if container['status'] == 'running' else "❌"
                health_str = f" ({container['health']})" if container.get('health') else ""
                lines.append(f"  • {container['name']}: {status_icon} {container['status']}{health_str}")

        lines.append("")
        lines.append(f"⏰ 报告时间: {self._get_current_time()}")

        return self.send('\n'.join(lines), msg_type='text')
