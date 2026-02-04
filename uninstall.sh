#!/bin/bash
# VPS 监控系统卸载脚本

set -e

INSTALL_DIR="/opt/vps-monitor"
SERVICE_FILE="/etc/systemd/system/vps-monitor.service"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
echo_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
echo_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 检查 root 权限
if [ "$EUID" -ne 0 ]; then
    echo_error "请使用 root 权限运行此脚本"
    exit 1
fi

echo_warn "即将卸载 VPS 监控系统"
read -p "确认卸载? (y/N): " confirm
if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
    echo_info "取消卸载"
    exit 0
fi

# 停止服务
echo_info "停止服务..."
systemctl stop vps-monitor 2>/dev/null || true
systemctl disable vps-monitor 2>/dev/null || true

# 删除服务文件
echo_info "删除 systemd 服务..."
rm -f "$SERVICE_FILE"
systemctl daemon-reload

# 询问是否删除安装目录
read -p "是否删除安装目录 $INSTALL_DIR? (y/N): " delete_dir
if [ "$delete_dir" = "y" ] || [ "$delete_dir" = "Y" ]; then
    echo_info "删除安装目录..."
    rm -rf "$INSTALL_DIR"
else
    echo_info "保留安装目录"
fi

echo ""
echo_info "卸载完成！"
