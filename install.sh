#!/bin/bash
# VPS 监控系统安装脚本
# 支持本地安装和远程一键安装
# 一键安装: curl -fsSL https://raw.githubusercontent.com/venomwise/vps-monitor/main/install.sh | sudo bash
# Service 覆盖策略: SERVICE_OVERWRITE_POLICY=prompt|keep|overwrite (默认: prompt)

set -euo pipefail

# GitHub Raw URL 基础地址
GITHUB_RAW_URL="https://raw.githubusercontent.com/venomwise/vps-monitor/main"

# 安装路径
INSTALL_DIR="/opt/vps-monitor"
SERVICE_NAME="vps-monitor.service"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}"
SERVICE_OVERWRITE_POLICY="${SERVICE_OVERWRITE_POLICY:-prompt}"

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

RUN_MODE=""
IS_UPDATE=false
HAS_PARTIAL_INSTALL=false
SERVICE_WAS_USABLE=false
WORK_DIR=""
STAGE_DIR=""
STAGE_APP_DIR=""
STAGE_SERVICE_FILE=""
STAGE_CONFIG_FILE=""
BACKUP_DIR=""
ROLLBACK_NEEDED=false
SERVICE_ACTION="replace"

# 检测运行模式：本地 or 远程
# 通过 curl | bash 运行时，脚本从 stdin 读取，没有实际的脚本文件路径
detect_run_mode() {
    # 检查是否从 stdin 运行（curl | bash 的情况）
    if [ -p /dev/stdin ] || [ ! -t 0 ]; then
        # 进一步检查：BASH_SOURCE[0] 是否指向一个真实存在的脚本文件
        if [ -z "${BASH_SOURCE[0]:-}" ] || [ ! -f "${BASH_SOURCE[0]}" ]; then
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

cleanup_temp_dir() {
    if [ -n "$WORK_DIR" ] && [ -d "$WORK_DIR" ]; then
        rm -rf "$WORK_DIR"
    fi
}

on_error() {
    local line="$1"
    echo_error "安装失败（行号: $line）"
    rollback_update
    exit 1
}

trap 'on_error $LINENO' ERR
trap cleanup_temp_dir EXIT

ensure_stage_layout() {
    mkdir -p "$INSTALL_DIR"
    WORK_DIR="$(mktemp -d "$INSTALL_DIR/.install-tmp.XXXXXX")"
    STAGE_DIR="$WORK_DIR/stage"
    STAGE_APP_DIR="$STAGE_DIR/app"
    STAGE_SERVICE_FILE="$STAGE_DIR/${SERVICE_NAME}"
    STAGE_CONFIG_FILE="$STAGE_DIR/config.yaml"

    mkdir -p "$STAGE_APP_DIR"
}

prepare_stage_from_remote() {
    local filepath

    echo_info "从 GitHub 下载程序文件到临时目录..."
    download_file "monitor.py" "$STAGE_APP_DIR/monitor.py"
    download_file "requirements.txt" "$STAGE_APP_DIR/requirements.txt"
    download_file "vps-monitor.service" "$STAGE_SERVICE_FILE"

    for filepath in "${PACKAGE_FILES[@]}"; do
        mkdir -p "$(dirname "$STAGE_APP_DIR/$filepath")"
        download_file "$filepath" "$STAGE_APP_DIR/$filepath"
    done

    # 配置文件：仅首次安装时下载
    if [ ! -f "$INSTALL_DIR/config.yaml" ]; then
        download_file "config.yaml" "$STAGE_CONFIG_FILE"
    fi
}

prepare_stage_from_local() {
    local script_dir
    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

    echo_info "从本地目录复制程序文件到临时目录..."
    cp "$script_dir/monitor.py" "$STAGE_APP_DIR/monitor.py"
    cp "$script_dir/requirements.txt" "$STAGE_APP_DIR/requirements.txt"
    cp "$script_dir/vps-monitor.service" "$STAGE_SERVICE_FILE"
    cp -a "$script_dir/vps_monitor" "$STAGE_APP_DIR/"

    # 配置文件：仅首次安装时复制
    if [ ! -f "$INSTALL_DIR/config.yaml" ]; then
        cp "$script_dir/config.yaml" "$STAGE_CONFIG_FILE"
    fi
}

assert_file_ready() {
    local filepath="$1"
    local desc="$2"

    if [ ! -s "$filepath" ]; then
        echo_error "$desc 不存在或为空: $filepath"
        return 1
    fi
}

verify_stage_files() {
    local filepath

    echo_info "校验临时目录文件完整性..."
    assert_file_ready "$STAGE_APP_DIR/monitor.py" "monitor.py"
    assert_file_ready "$STAGE_APP_DIR/requirements.txt" "requirements.txt"
    assert_file_ready "$STAGE_SERVICE_FILE" "service 文件"

    for filepath in "${PACKAGE_FILES[@]}"; do
        assert_file_ready "$STAGE_APP_DIR/$filepath" "$filepath"
    done

    echo_info "校验 Python 文件语法..."
    python3 -m py_compile "$STAGE_APP_DIR/monitor.py"
    for filepath in "${PACKAGE_FILES[@]}"; do
        python3 -m py_compile "$STAGE_APP_DIR/$filepath"
    done
}

is_service_usable() {
    if [ ! -f "$SERVICE_FILE" ]; then
        return 1
    fi

    local load_state
    load_state="$(systemctl show -p LoadState --value "$SERVICE_NAME" 2>/dev/null || true)"

    if [ -z "$load_state" ] || [ "$load_state" = "not-found" ]; then
        systemctl daemon-reload >/dev/null 2>&1 || true
        load_state="$(systemctl show -p LoadState --value "$SERVICE_NAME" 2>/dev/null || true)"
    fi

    [ -n "$load_state" ] && [ "$load_state" != "not-found" ]
}

is_install_dir_complete() {
    local filepath

    [ -f "$INSTALL_DIR/monitor.py" ] || return 1
    [ -f "$INSTALL_DIR/requirements.txt" ] || return 1

    for filepath in "${PACKAGE_FILES[@]}"; do
        [ -f "$INSTALL_DIR/$filepath" ] || return 1
    done

    return 0
}

has_install_artifacts() {
    [ -f "$INSTALL_DIR/monitor.py" ] \
        || [ -d "$INSTALL_DIR/vps_monitor" ] \
        || [ -f "$INSTALL_DIR/requirements.txt" ] \
        || [ -f "$SERVICE_FILE" ]
}

detect_install_state() {
    if is_service_usable; then
        SERVICE_WAS_USABLE=true
    fi

    if [ "$SERVICE_WAS_USABLE" = true ] && is_install_dir_complete; then
        IS_UPDATE=true
        echo_info "检测到已有完整安装，执行更新..."
        return
    fi

    if has_install_artifacts; then
        HAS_PARTIAL_INSTALL=true
        echo_warn "检测到不完整安装痕迹，将执行修复安装并保留回滚能力"
    else
        echo_info "开始全新安装 VPS 监控系统..."
    fi
}

create_backup() {
    local ts
    ts="$(date +%Y%m%d-%H%M%S)"

    BACKUP_DIR="$INSTALL_DIR/backups/update-${ts}"
    mkdir -p "$BACKUP_DIR"

    echo_info "创建更新备份: $BACKUP_DIR"

    if [ -f "$INSTALL_DIR/monitor.py" ]; then
        cp -a "$INSTALL_DIR/monitor.py" "$BACKUP_DIR/monitor.py"
    fi

    if [ -f "$INSTALL_DIR/requirements.txt" ]; then
        cp -a "$INSTALL_DIR/requirements.txt" "$BACKUP_DIR/requirements.txt"
    fi

    if [ -d "$INSTALL_DIR/vps_monitor" ]; then
        cp -a "$INSTALL_DIR/vps_monitor" "$BACKUP_DIR/vps_monitor"
    fi

    if [ -f "$SERVICE_FILE" ]; then
        cp -a "$SERVICE_FILE" "$BACKUP_DIR/${SERVICE_NAME}"
    fi
}

rollback_update() {
    if [ "$ROLLBACK_NEEDED" != true ] || [ -z "$BACKUP_DIR" ] || [ ! -d "$BACKUP_DIR" ]; then
        return
    fi

    set +e
    echo_warn "开始回滚到更新前版本..."

    if [ -d "$BACKUP_DIR/vps_monitor" ]; then
        rm -rf "$INSTALL_DIR/vps_monitor"
        cp -a "$BACKUP_DIR/vps_monitor" "$INSTALL_DIR/vps_monitor"
    fi

    if [ -f "$BACKUP_DIR/monitor.py" ]; then
        cp -a "$BACKUP_DIR/monitor.py" "$INSTALL_DIR/monitor.py"
    fi

    if [ -f "$BACKUP_DIR/requirements.txt" ]; then
        cp -a "$BACKUP_DIR/requirements.txt" "$INSTALL_DIR/requirements.txt"
    fi

    if [ -f "$BACKUP_DIR/${SERVICE_NAME}" ]; then
        cp -a "$BACKUP_DIR/${SERVICE_NAME}" "$SERVICE_FILE"
    fi

    systemctl daemon-reload >/dev/null 2>&1 || true
    systemctl restart "$SERVICE_NAME" >/dev/null 2>&1 || true

    echo_warn "回滚完成，请执行: sudo systemctl status vps-monitor"
}

decide_service_action() {
    SERVICE_ACTION="replace"

    if [ ! -f "$SERVICE_FILE" ]; then
        return
    fi

    if cmp -s "$SERVICE_FILE" "$STAGE_SERVICE_FILE"; then
        SERVICE_ACTION="unchanged"
        return
    fi

    case "$SERVICE_OVERWRITE_POLICY" in
        overwrite)
            SERVICE_ACTION="replace"
            echo_warn "检测到 service 差异，按策略覆盖本地 service"
            ;;
        keep)
            SERVICE_ACTION="keep"
            echo_warn "检测到 service 差异，按策略保留本地 service"
            ;;
        prompt)
            if [ -t 0 ]; then
                local answer
                read -r -p "检测到本地 service 有修改，是否覆盖为新版本? [y/N]: " answer
                if [[ "$answer" =~ ^[Yy]$ ]]; then
                    SERVICE_ACTION="replace"
                else
                    SERVICE_ACTION="keep"
                fi
            else
                SERVICE_ACTION="keep"
                echo_warn "非交互模式下默认保留本地 service（可用 SERVICE_OVERWRITE_POLICY=overwrite 强制覆盖）"
            fi
            ;;
        *)
            SERVICE_ACTION="keep"
            echo_warn "未知 SERVICE_OVERWRITE_POLICY=$SERVICE_OVERWRITE_POLICY，默认保留本地 service"
            ;;
    esac
}

atomic_replace_file() {
    local src="$1"
    local dst="$2"
    local tmp_dst="${dst}.new.$$"

    mv "$src" "$tmp_dst"
    mv -f "$tmp_dst" "$dst"
}

atomic_replace_dir() {
    local src="$1"
    local dst="$2"
    local old_dst="${dst}.old.$$"

    if [ -d "$dst" ]; then
        mv "$dst" "$old_dst"
    fi

    mv "$src" "$dst"
    if [ -d "$old_dst" ]; then
        rm -rf "$old_dst"
    fi
}

apply_staged_files() {
    mkdir -p "$INSTALL_DIR"
    mkdir -p "$INSTALL_DIR/logs"

    atomic_replace_file "$STAGE_APP_DIR/monitor.py" "$INSTALL_DIR/monitor.py"
    atomic_replace_file "$STAGE_APP_DIR/requirements.txt" "$INSTALL_DIR/requirements.txt"
    atomic_replace_dir "$STAGE_APP_DIR/vps_monitor" "$INSTALL_DIR/vps_monitor"

    if [ ! -f "$INSTALL_DIR/config.yaml" ] && [ -f "$STAGE_CONFIG_FILE" ]; then
        mv "$STAGE_CONFIG_FILE" "$INSTALL_DIR/config.yaml"
        echo_info "已安装配置文件模板，请编辑 $INSTALL_DIR/config.yaml"
    elif [ -f "$INSTALL_DIR/config.yaml" ]; then
        echo_warn "配置文件已存在，跳过覆盖"
    fi

    case "$SERVICE_ACTION" in
        replace)
            atomic_replace_file "$STAGE_SERVICE_FILE" "$SERVICE_FILE"
            ;;
        unchanged)
            echo_info "service 文件无变化，跳过覆盖"
            ;;
        keep)
            echo_warn "保留本地 service 文件: $SERVICE_FILE"
            ;;
    esac
}

run_startup_probe() {
    (
        cd "$INSTALL_DIR"
        python3 -c "import monitor; import vps_monitor" >/dev/null 2>&1
    )
}

check_service_health() {
    local retries=12
    local i

    for i in $(seq 1 "$retries"); do
        if systemctl is-active --quiet "$SERVICE_NAME"; then
            if run_startup_probe; then
                return 0
            fi
        fi
        sleep 1
    done

    return 1
}

# 检查 root 权限
if [ "$EUID" -ne 0 ]; then
    echo_error "请使用 root 权限运行此脚本"
    exit 1
fi

# 检查 curl（远程模式需要）
if ! command -v curl >/dev/null 2>&1; then
    echo_error "未找到 curl，请先安装："
    echo "  Ubuntu/Debian: sudo apt install -y curl"
    echo "  CentOS/RHEL:   sudo yum install -y curl"
    exit 1
fi

# 检查 Python3 和 pip3
if ! command -v python3 >/dev/null 2>&1; then
    echo_error "未找到 python3，请先安装 Python 3.9+"
    exit 1
fi

if ! command -v pip3 >/dev/null 2>&1; then
    echo_error "未找到 pip3，请先安装："
    echo "  Ubuntu/Debian: sudo apt install -y python3-pip"
    echo "  CentOS/RHEL:   sudo yum install -y python3-pip"
    exit 1
fi

# 检测运行模式
RUN_MODE="$(detect_run_mode)"
echo_info "检测到运行模式: $RUN_MODE"

# 更可靠安装判定
detect_install_state

# 准备临时目录并拉取文件
ensure_stage_layout
if [ "$RUN_MODE" = "remote" ]; then
    prepare_stage_from_remote
else
    prepare_stage_from_local
fi

verify_stage_files

decide_service_action

# 更新或修复安装前先备份，确保可回滚
if [ "$IS_UPDATE" = true ] || [ "$HAS_PARTIAL_INSTALL" = true ]; then
    create_backup
fi

# 在切换前先安装依赖，避免替换后才发现依赖失败
echo_info "安装 Python 依赖..."
pip3 install -r "$STAGE_APP_DIR/requirements.txt" -q

ROLLBACK_NEEDED=true
apply_staged_files

# 重新加载 systemd 配置
echo_info "配置 systemd 服务..."
systemctl daemon-reload

# 启用服务
echo_info "启用开机自启..."
systemctl enable "$SERVICE_NAME"

if [ "$SERVICE_WAS_USABLE" = true ]; then
    echo_info "重启服务..."
    systemctl restart "$SERVICE_NAME"

    echo_info "执行健康检查（systemctl is-active + 启动探针）..."
    if ! check_service_health; then
        echo_error "健康检查失败，触发自动回滚"
        rollback_update
        exit 1
    fi

    ROLLBACK_NEEDED=false

    echo ""
    echo_info "更新完成！服务健康检查通过。"
    echo ""
    echo "查看服务状态: sudo systemctl status vps-monitor"
    echo "查看日志: sudo journalctl -u vps-monitor -f"
else
    ROLLBACK_NEEDED=false

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
if [ -n "$BACKUP_DIR" ] && [ -d "$BACKUP_DIR" ]; then
    echo_info "备份目录: $BACKUP_DIR"
fi
