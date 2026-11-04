#!/usr/bin/env bash
# ============================================================================
# Antigravity CLI 中文深度增强与渲染修复套件 (antigravity-chinese)
# 一键安装、构建与模式管理脚本
# ============================================================================
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCH_SCRIPT="$PROJECT_ROOT/scripts/patch_agy.py"
VERIFY_SCRIPT="$PROJECT_ROOT/scripts/verify_patch.py"
SWITCH_SCRIPT="$PROJECT_ROOT/scripts/switch_mode.sh"

GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_banner() {
    echo -e "${CYAN}============================================================${NC}"
    echo -e "${CYAN}   Antigravity CLI 中文深度增强与渲染修复套件 (v1.5.0)      ${NC}"
    echo -e "${CYAN}   - 解锁 Bash 中文摘要 | 解除思考 '...' 截断               ${NC}"
    echo -e "${CYAN}   - 原生界面词条汉化   | 修复中文引用块右侧吞字            ${NC}"
    echo -e "${CYAN}   - 融合 Codex 阶段简报与 Claude 极简中文笔记体思考规范    ${NC}"
    echo -e "${CYAN}============================================================${NC}"
}

run_isolated() {
    echo -e "${GREEN}>>> [1/2] 正在隔离目录 ./bin/agy-zh 构建中文增强版（不改动原版 agy）...${NC}"
    python3 "$PATCH_SCRIPT"
    echo -e "${GREEN}>>> [2/2] 正在执行完整性与渲染验证...${NC}"
    python3 "$VERIFY_SCRIPT"
    echo -e "\n${GREEN}[完成] 隔离版已就绪！您可以通过以下命令直接体验：${NC}"
    echo -e "  ${YELLOW}$PROJECT_ROOT/bin/agy-zh${NC}        (直连模式)"
    echo -e "  ${YELLOW}$PROJECT_ROOT/bin/agy-zh-proxy${NC}  (代理模式)"
}

run_global() {
    python3 "$PATCH_SCRIPT"
    "$SWITCH_SCRIPT" apply-rules
    "$SWITCH_SCRIPT" enable-global
    "$SWITCH_SCRIPT" status
}

case "${1:-menu}" in
    --isolated|-i)
        print_banner
        run_isolated
        ;;
    --global|-g)
        print_banner
        run_global
        ;;
    --rules-only|-r)
        print_banner
        "$SWITCH_SCRIPT" apply-rules
        ;;
    --restore|--uninstall|-u)
        print_banner
        "$SWITCH_SCRIPT" restore
        ;;
    --status|-s)
        "$SWITCH_SCRIPT" status
        ;;
    menu|*)
        print_banner
        "$SWITCH_SCRIPT" status
        echo ""
        echo "请选择操作模式："
        echo "  1) 构建隔离版 (推荐：仅生成 ./bin/agy-zh，完全不动原版 ~/.local/bin/agy)"
        echo "  2) 启用全局中文增强版 (原子替换 ~/.local/bin/agy + 写入增强中文规则，自动备份)"
        echo "  3) 仅更新全局中文思考与进度简报规则 (~/.gemini/GEMINI.md)"
        echo "  4) 运行自动化验证测试 (verify_patch.py)"
        echo "  5) 一键无损还原原版 Antigravity CLI 与原有规则"
        echo "  0) 退出"
        echo ""
        read -rp "请输入选项编号 [0-5]: " choice
        case "$choice" in
            1) run_isolated ;;
            2) run_global ;;
            3) "$SWITCH_SCRIPT" apply-rules ;;
            4) python3 "$VERIFY_SCRIPT" ;;
            5) "$SWITCH_SCRIPT" restore ;;
            0) exit 0 ;;
            *) echo "无效选项: $choice"; exit 1 ;;
        esac
        ;;
esac
