#!/bin/bash
# VPS 监控系统安装脚本
# 支持本地安装和远程一键安装
# 一键安装: curl -fsSL https://raw.githubusercontent.com/venomwise/vps-monitor/main/install.sh | sudo bash

set -e

# GitHub Raw URL 基础地址
GITHUB_RAW_URL="https://raw.githubusercontent.com/venomwise/vps-monitor/main"

# 安装路径
INSTALL_DIR="/opt/vps-monitor"
SERVICE_FILE="/etc/systemd/system/vps-monitor.service"

# Python 包文件清单（远程模式逐个下载）
PACKAGE_FILES=(
    "vps_monitor/__init__.py"
    "vps_monitor/app.py"
    "vps_monitor/config.py"
    "vps_monitor/notifier.py"
    "vps_monitor/scheduler.py"
    "vps_monitor/state.py"
    "vps_monitor/collectors/__init__.py"
    "vps_monitor/collectors/system.py"
    "vps_monitor/collectors/network.py"
    "vps_monitor/collectors/docker.py"
)

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
echo_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
echo_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 检测运行模式：本地 or 远程
# 通过 curl | bash 运行时，脚本从 stdin 读取，没有实际的脚本文件路径
detect_run_mode() {
    # 检查是否从 stdin 运行（curl | bash 的情况）
    if [ -p /dev/stdin ] || [ ! -t 0 ]; then
        # 进一步检查：BASH_SOURCE[0] 是否指向一个真实存在的脚本文件
        if [ -z "${BASH_SOURCE[0]}" ] || [ ! -f "${BASH_SOURCE[0]}" ]; then
            echo "remote"
            return
        fi
    fi

    # 检查脚本所在目录是否有 monitor.py（本地模式的标志）
    local script_dir
    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]:-/tmp}")" 2>/dev/null && pwd)" || script_dir="/tmp"
    if [ -f "$script_dir/monitor.py" ]; then
        echo "local"
    else
        echo "remote"
    fi
}

# 从 GitHub 下载文件
download_file() {
    local filename="$1"
    local dest="$2"
    local url="${GITHUB_RAW_URL}/${filename}"

    if ! curl -fsSL "$url" -o "$dest"; then
        echo_error "下载 $filename 失败"
        return 1
    fi
}

download_package_files() {
    local filepath
    for filepath in "${PACKAGE_FILES[@]}"; do
        mkdir -p "$(dirname "$INSTALL_DIR/$filepath")"
        download_file "$filepath" "$INSTALL_DIR/$filepath"
    done
}

# 检查 root 权限
if [ "$EUID" -ne 0 ]; then
    echo_error "请使用 root 权限运行此脚本"
    exit 1
fi

# 检查 curl（远程模式需要）
if ! command -v curl &> /dev/null; then
    echo_error "未找到 curl，请先安装："
    echo "  Ubuntu/Debian: sudo apt install -y curl"
    echo "  CentOS/RHEL:   sudo yum install -y curl"
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

# 检测运行模式
RUN_MODE=$(detect_run_mode)
echo_info "检测到运行模式: $RUN_MODE"

# 检测是否为更新安装
IS_UPDATE=false
if [ -f "$INSTALL_DIR/monitor.py" ]; then
    IS_UPDATE=true
    echo_info "检测到已有安装，执行更新..."
else
    echo_info "开始全新安装 VPS 监控系统..."
fi

# 创建安装目录
echo_info "创建安装目录: $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR/logs"

# 根据运行模式获取文件
if [ "$RUN_MODE" = "remote" ]; then
    # 远程模式：从 GitHub 下载文件
    echo_info "从 GitHub 下载程序文件..."

    download_file "monitor.py" "$INSTALL_DIR/monitor.py"
    download_file "requirements.txt" "$INSTALL_DIR/requirements.txt"
    download_file "vps-monitor.service" "$SERVICE_FILE"
    download_package_files

    # 配置文件：仅首次安装时下载
    if [ "$IS_UPDATE" = false ]; then
        download_file "config.yaml" "$INSTALL_DIR/config.yaml"
        echo_info "已下载配置文件模板，请编辑 $INSTALL_DIR/config.yaml"
    else
        echo_warn "配置文件已存在，跳过下载（请手动更新配置）"
    fi
else
    # 本地模式：从本地目录复制文件
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

    if [ "$SCRIPT_DIR" = "$INSTALL_DIR" ]; then
        echo_info "检测到已在安装目录运行，跳过文件复制"
    else
        echo_info "复制程序文件..."
        cp "$SCRIPT_DIR/monitor.py" "$INSTALL_DIR/"
        cp "$SCRIPT_DIR/requirements.txt" "$INSTALL_DIR/"
        cp "$SCRIPT_DIR/vps-monitor.service" "$SERVICE_FILE"
        cp -r "$SCRIPT_DIR/vps_monitor" "$INSTALL_DIR/"

        # 配置文件：仅首次安装时复制
        if [ "$IS_UPDATE" = false ]; then
            cp "$SCRIPT_DIR/config.yaml" "$INSTALL_DIR/"
            echo_info "已复制配置文件模板，请编辑 $INSTALL_DIR/config.yaml"
        else
            echo_warn "配置文件已存在，跳过复制（请手动更新配置）"
        fi
    fi
fi

# 安装 Python 依赖
echo_info "安装 Python 依赖..."
if ! pip3 install -r "$INSTALL_DIR/requirements.txt" -q; then
    echo_error "Python 依赖安装失败，请检查网络连接或手动安装"
    exit 1
fi

# 重新加载 systemd 配置
echo_info "配置 systemd 服务..."
systemctl daemon-reload

# 启用服务
echo_info "启用开机自启..."
systemctl enable vps-monitor

# 如果是更新，自动重启服务
if [ "$IS_UPDATE" = true ]; then
    echo_info "重启服务..."
    systemctl restart vps-monitor
    echo ""
    echo_info "更新完成！服务已重启。"
    echo ""
    echo "查看服务状态: sudo systemctl status vps-monitor"
    echo "查看日志: sudo journalctl -u vps-monitor -f"
else
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
fi
echo ""
