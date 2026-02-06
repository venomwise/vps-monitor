#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""VPS 监控系统入口文件。"""

import sys
from pathlib import Path

from vps_monitor.app import VPSMonitor


def main():
    """主函数"""
    project_dir = Path(__file__).resolve().parent
    config_path = project_dir / 'config.yaml'

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
