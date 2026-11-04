#!/usr/bin/env bash
# Antigravity CLI 中文增强版 — 状态检查、规则应用与安全切换工具
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORIG_AGY="$(command -v agy 2>/dev/null || echo "$HOME/.local/bin/agy")"
BACKUP_AGY="$PROJECT_ROOT/bin/agy.orig"
ZH_AGY="$PROJECT_ROOT/bin/agy-zh"
ZH_PROXY="$PROJECT_ROOT/bin/agy-zh-proxy"
GLOBAL_RULE="$HOME/.gemini/GEMINI.md"
BACKUP_RULE="$PROJECT_ROOT/rules/GEMINI.md.bak"
ENHANCED_RULE="$PROJECT_ROOT/rules/GEMINI_ZH_BEST_PRACTICES.md"

show_status() {
    echo "============================================================"
    echo "       Antigravity CLI 中文增强工程状态检查"
    echo "============================================================"
    if [[ -f "$ORIG_AGY" ]]; then
        echo "[原版 CLI]     $ORIG_AGY (SHA256: $(sha256sum "$ORIG_AGY" | awk '{print substr($1,1,16)}'))..."
    fi
    if [[ -f "$BACKUP_AGY" ]]; then
        echo "[隔离备份]     $BACKUP_AGY (SHA256: $(sha256sum "$BACKUP_AGY" | awk '{print substr($1,1,16)}'))..."
    fi
    if [[ -f "$ZH_AGY" ]]; then
        echo "[中文增强版]   $ZH_AGY (SHA256: $(sha256sum "$ZH_AGY" | awk '{print substr($1,1,16)}'))..."
    fi
    echo "------------------------------------------------------------"
    if [[ -f "$ORIG_AGY" && -f "$BACKUP_AGY" ]]; then
        if cmp -s "$ORIG_AGY" "$BACKUP_AGY"; then
            echo "[当前模式]     隔离安全模式（~/.local/bin/agy 仍为 100% 原版二进制）"
        elif cmp -s "$ORIG_AGY" "$ZH_AGY"; then
            echo "[当前模式]     全局中文增强模式（~/.local/bin/agy 已切换为中文增强版）"
        else
            echo "[当前模式]     未知/已更新版本（请重新运行 patch_agy.py）"
        fi
    fi
    if [[ -f "$GLOBAL_RULE" && -f "$ENHANCED_RULE" ]]; then
        if cmp -s "$GLOBAL_RULE" "$ENHANCED_RULE"; then
            echo "[全局规则]     已启用增强版中文规范 (Codex + Claude Code 融合版)"
        else
            echo "[全局规则]     当前为原有规则（未覆盖，可通过 '$0 apply-rules' 启用增强规则）"
        fi
    fi
    echo "============================================================"
}

apply_rules() {
    mkdir -p "$(dirname "$GLOBAL_RULE")"
    if [[ -f "$GLOBAL_RULE" && ! -f "$BACKUP_RULE" ]]; then
        cp -p "$GLOBAL_RULE" "$BACKUP_RULE"
        echo "[备份] 已将原有 ~/.gemini/GEMINI.md 备份至: $BACKUP_RULE"
    fi
    cp "$ENHANCED_RULE" "$GLOBAL_RULE"
    if [[ -x "$HOME/miniconda3/bin/tectonic" ]]; then
        printf '\n- **LaTeX 编译工具**：本机已安装 Tectonic（路径：`%s/miniconda3/bin/tectonic`），将 LaTeX 编译为 PDF 时可直接使用 Tectonic。\n' "$HOME" >> "$GLOBAL_RULE"
    fi
    echo "[成功] 已将 Codex + Claude Code 融合版中文规范写入: $GLOBAL_RULE"
}

enable_global() {
    if [[ ! -x "$ZH_AGY" ]]; then
        echo "[错误] 尚未生成 $ZH_AGY，请先运行 python3 scripts/patch_agy.py" >&2
        exit 1
    fi
    if [[ ! -f "$BACKUP_AGY" ]]; then
        cp -p "$ORIG_AGY" "$BACKUP_AGY"
    fi
    # 使用临时文件 + mv 原子替换，防止正在运行的 agy 进程触发 Text file busy
    cp -p "$ZH_AGY" "${ORIG_AGY}.tmp"
    mv -f "${ORIG_AGY}.tmp" "$ORIG_AGY"
    echo "[成功] 已将 ~/.local/bin/agy 原子切换为中文增强版！"
}

restore_original() {
    if [[ -f "$BACKUP_AGY" ]]; then
        cp -p "$BACKUP_AGY" "${ORIG_AGY}.tmp"
        mv -f "${ORIG_AGY}.tmp" "$ORIG_AGY"
        echo "[还原] 已将 ~/.local/bin/agy 无损恢复为原版二进制。"
    fi
    if [[ -f "$BACKUP_RULE" ]]; then
        cp -p "$BACKUP_RULE" "$GLOBAL_RULE"
        echo "[还原] 已将 ~/.gemini/GEMINI.md 恢复为原有规则。"
    fi
}

case "${1:-status}" in
    status)
        show_status
        ;;
    apply-rules)
        apply_rules
        ;;
    enable-global)
        enable_global
        ;;
    restore)
        restore_original
        ;;
    *)
        echo "用法: $0 {status|apply-rules|enable-global|restore}"
        exit 2
        ;;
esac
