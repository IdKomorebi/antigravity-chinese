#!/usr/bin/env bash
# ============================================================================
# Antigravity CLI 中文原生思考槽位合流与渲染修复套件 (antigravity-chinese v2)
# 支持 macOS Apple Silicon (arm64, v1.5.4) 与 Linux (x86_64, v1.5.0)
# ============================================================================
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCH_SCRIPT="${PROJECT_ROOT}/scripts/patch_agy.py"
VERIFY_SCRIPT="${PROJECT_ROOT}/scripts/verify_patch.py"
SWITCH_SCRIPT="${PROJECT_ROOT}/scripts/switch_mode.sh"

chmod +x "${PATCH_SCRIPT}" "${VERIFY_SCRIPT}" "${SWITCH_SCRIPT}" 2>/dev/null || true

GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_banner() {
    echo -e "${CYAN}============================================================${NC}"
    echo -e "${CYAN}   Antigravity CLI 中文原生思考合流与渲染修复套件 (v2)      ${NC}"
    echo -e "${CYAN}   - 原生 ▸ Thought 槽位中文合流 | 杜绝流式先吐后吞闪烁     ${NC}"
    echo -e "${CYAN}   - 解除单行 '...' 省略号腰斩   | 修复 Markdown 右侧吞字   ${NC}"
    echo -e "${CYAN}   - 解放内部完整推理深度        | 自动 Mach-O 代码重签名   ${NC}"
    echo -e "${CYAN}============================================================${NC}"
}

run_isolated() {
    echo -e "${GREEN}>>> [1/2] 正在隔离目录 ./bin/agy-zh 构建中文增强版（不改动系统原版 agy）...${NC}"
    python3 "${PATCH_SCRIPT}"
    echo -e "${GREEN}>>> [2/2] 正在执行完整性与代码签名核验...${NC}"
    python3 "${VERIFY_SCRIPT}" --binary "${PROJECT_ROOT}/bin/agy-zh"
    echo -e "\n${GREEN}[完成] 隔离版已就绪！您可以通过以下命令直接体验：${NC}"
    echo -e "  ${YELLOW}${PROJECT_ROOT}/bin/agy-zh${NC}"
}

run_global() {
    local ui_flag="${1:-enable}"
    "${SWITCH_SCRIPT}" "${ui_flag}"
    python3 "${VERIFY_SCRIPT}"
}

case "${1:---global}" in
    --global|-g)
        print_banner
        run_global "enable"
        ;;
    --ui-zh)
        print_banner
        run_global "enable-ui"
        ;;
    --isolated|-i)
        print_banner
        run_isolated
        ;;
    --rules-only|-r)
        print_banner
        "${SWITCH_SCRIPT}" apply-rules
        ;;
    --restore|--uninstall|-u)
        print_banner
        "${SWITCH_SCRIPT}" restore
        ;;
    --status|-s)
        "${SWITCH_SCRIPT}" status
        ;;
    menu)
        print_banner
        "${SWITCH_SCRIPT}" status
        echo ""
        echo "请选择操作模式："
        echo "  1) 启用全局中文原生思考增强版 (推荐：保留官方英文标签，▸ Thought 内直接合流自然中文思考)"
        echo "  2) 启用全量 UI 汉化模式 (同时将 Thought for / ctrl+o 等界面词条汉化为中文)"
        echo "  3) 仅构建隔离版 (仅生成 ./bin/agy-zh，不修改 ~/.local/bin/agy)"
        echo "  4) 仅更新全局中文思考规范 (~/.gemini/config/GEMINI.md)"
        echo "  5) 运行自动化核验 (verify_patch.py)"
        echo "  6) 一键无损还原官方原版 Antigravity CLI 与原有规则"
        echo "  0) 退出"
        echo ""
        read -rp "请输入选项编号 [0-6]: " choice
        case "${choice}" in
            1) run_global "enable" ;;
            2) run_global "enable-ui" ;;
            3) run_isolated ;;
            4) "${SWITCH_SCRIPT}" apply-rules ;;
            5) python3 "${VERIFY_SCRIPT}" ;;
            6) "${SWITCH_SCRIPT}" restore ;;
            0) exit 0 ;;
            *) echo "无效选项: ${choice}"; exit 1 ;;
        esac
        ;;
    *)
        echo "用法: $0 [--global | --ui-zh | --isolated | --rules-only | --restore | --status | menu]"
        exit 1
        ;;
esac
