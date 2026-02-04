#!/bin/bash
# VPS 监控系统安装脚本

set -e

INSTALL_DIR="/opt/vps-monitor"
SERVICE_FILE="/etc/systemd/system/vps-monitor.service"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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

# 检查 Python3 和 pip3
if ! command -v python3 &> /dev/null; then
    echo_error "未找到 python3，请先安装 Python 3.9+"
    exit 1
fi

if ! command -v pip3 &> /dev/null; then
    echo_error "未找到 pip3，请先安装："
    echo "  Ubuntu/Debian: sudo apt install -y python3-pip"
    echo "  CentOS/RHEL:   sudo yum install -y python3-pip"
    exit 1
fi

echo_info "开始安装 VPS 监控系统..."

# 创建安装目录
echo_info "创建安装目录: $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR/logs"

# 复制文件（如果源目录和安装目录不同）
if [ "$SCRIPT_DIR" = "$INSTALL_DIR" ]; then
    echo_info "检测到已在安装目录运行，跳过文件复制"
else
    echo_info "复制程序文件..."
    cp "$SCRIPT_DIR/monitor.py" "$INSTALL_DIR/"
    cp "$SCRIPT_DIR/requirements.txt" "$INSTALL_DIR/"

    # 检查配置文件
    if [ -f "$INSTALL_DIR/config.yaml" ]; then
        echo_warn "配置文件已存在，跳过复制（请手动更新配置）"
    else
        cp "$SCRIPT_DIR/config.yaml" "$INSTALL_DIR/"
        echo_info "已复制配置文件模板，请编辑 $INSTALL_DIR/config.yaml"
    fi
fi

# 安装 Python 依赖
echo_info "安装 Python 依赖..."
if ! pip3 install -r "$INSTALL_DIR/requirements.txt" -q; then
    echo_error "Python 依赖安装失败，请检查网络连接或手动安装"
    exit 1
fi

# 安装 systemd 服务
echo_info "安装 systemd 服务..."
cp "$SCRIPT_DIR/vps-monitor.service" "$SERVICE_FILE"
systemctl daemon-reload

# 启用服务
echo_info "启用开机自启..."
systemctl enable vps-monitor

echo ""
echo_info "安装完成！"
echo ""
echo "后续步骤:"
echo "  1. 编辑配置文件: sudo vim $INSTALL_DIR/config.yaml"
echo "  2. 填入企业微信 Webhook URL"
echo "  3. 配置要监控的 Docker 容器"
echo "  4. 启动服务: sudo systemctl start vps-monitor"
echo "  5. 查看状态: sudo systemctl status vps-monitor"
echo "  6. 查看日志: sudo journalctl -u vps-monitor -f"
echo ""
