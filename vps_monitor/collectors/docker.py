"""Docker container status collector."""

import logging
from typing import Dict, List, Optional

from ..config import ConfigManager

try:
    import docker
    DOCKER_AVAILABLE = True
except ImportError:
    docker = None  # type: ignore
    DOCKER_AVAILABLE = False


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

            if status['status'] != 'running':
                alerts.append({
                    'key': f'docker_{name}_status',
                    'container': name,
                    'type': 'status',
                    'current': status['status'],
                    'expected': 'running'
                })

            if check_health and status['health'] and status['health'] != 'healthy':
                alerts.append({
                    'key': f'docker_{name}_health',
                    'container': name,
                    'type': 'health',
                    'current': status['health'],
                    'expected': 'healthy'
                })

        return alerts
