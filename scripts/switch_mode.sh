#!/usr/bin/env bash
# Antigravity CLI 中文原生思考合流套件 — 状态检查、规则应用与安全切换工具 (跨平台版)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
AGY_BIN="${HOME}/.local/bin/agy"
if [[ ! -f "${AGY_BIN}" ]]; then
    AGY_BIN="$(type -P agy 2>/dev/null || echo "${HOME}/.local/bin/agy")"
fi
ORIG_BIN="${PROJECT_ROOT}/bin/agy.orig"
ZH_BIN="${PROJECT_ROOT}/bin/agy-zh"
RULE_SRC="${PROJECT_ROOT}/rules/GEMINI_ZH_BEST_PRACTICES.md"
MERGED_RULE="${PROJECT_ROOT}/bin/GEMINI.merged.md"
GLOBAL_CONFIG_DIR="${HOME}/.gemini/config"
GLOBAL_CONFIG_RULE="${GLOBAL_CONFIG_DIR}/GEMINI.md"
HOME_GEMINI_RULE="${HOME}/.gemini/GEMINI.md"
BACKUP_RULE="${PROJECT_ROOT}/rules/GEMINI.md.bak"
BACKUP_CONFIG_RULE="${PROJECT_ROOT}/rules/GEMINI.config.md.bak"

calc_sha256() {
    local target="$1"
    if command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "${target}" | awk '{print $1}'
    elif command -v sha256sum >/dev/null 2>&1; then
        sha256sum "${target}" | awk '{print $1}'
    else
        python3 -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "${target}"
    fi
}

usage() {
    cat <<EOF
用法: $(basename "$0") <命令>

命令:
  enable         启用全局中文增强版 (保留官方原生 Thought for 标签，底层合流自然中文思考)
  enable-ui      启用全量 UI 汉化模式 (同时汉化 Thought for / ctrl+o 等界面状态词条)
  enable-global  同 enable (向下兼容原脚本参数)
  apply-rules    仅挂载全局中文思考规则 (~/.gemini/config/GEMINI.md & ~/.gemini/GEMINI.md)
  disable        完全恢复官方原版 agy 二进制与原有规则配置
  restore        同 disable (向下兼容原脚本参数)
  status         查看当前 agy 二进制、代码签名与全局中文规则状态
EOF
}

ensure_backup() {
    mkdir -p "${PROJECT_ROOT}/bin"
    if [[ ! -f "${AGY_BIN}" ]]; then
        echo "[错误] 未找到 ${AGY_BIN}" >&2
        exit 1
    fi
    if [[ ! -f "${ORIG_BIN}" ]]; then
        cp -p "${AGY_BIN}" "${ORIG_BIN}"
        echo "[备份] 已将原版 agy 安全备份至: ${ORIG_BIN}"
    else
        local sys_ver orig_ver
        sys_ver="$("${AGY_BIN}" --version 2>/dev/null || true)"
        orig_ver="$("${ORIG_BIN}" --version 2>/dev/null || true)"
        if [[ -n "${sys_ver}" && -n "${orig_ver}" && "${sys_ver}" != "${orig_ver}" ]]; then
            echo "[升级同步] 检测到系统 agy 已从 ${orig_ver} 升级至 ${sys_ver}，正在更新原版备份..."
            cp -p "${AGY_BIN}" "${ORIG_BIN}"
        fi
    fi
}

install_rules() {
    mkdir -p "${GLOBAL_CONFIG_DIR}" "${PROJECT_ROOT}/bin"
    if [[ -f "${HOME_GEMINI_RULE}" && ! -L "${HOME_GEMINI_RULE}" && ! -f "${BACKUP_RULE}" ]]; then
        cp -p "${HOME_GEMINI_RULE}" "${BACKUP_RULE}"
        echo "[备份] 已将原有 ~/.gemini/GEMINI.md 备份至: ${BACKUP_RULE}"
    fi
    if [[ -f "${GLOBAL_CONFIG_RULE}" && ! -L "${GLOBAL_CONFIG_RULE}" && ! -f "${BACKUP_CONFIG_RULE}" ]]; then
        cp -p "${GLOBAL_CONFIG_RULE}" "${BACKUP_CONFIG_RULE}"
        echo "[备份] 已将原有 ~/.gemini/config/GEMINI.md 备份至: ${BACKUP_CONFIG_RULE}"
    fi
    local target_rule="${RULE_SRC}"
    if [[ -x "${HOME}/miniconda3/bin/tectonic" ]]; then
        cp "${RULE_SRC}" "${MERGED_RULE}"
        printf '\n- **LaTeX 编译工具**：本机已安装 Tectonic（路径：`%s/miniconda3/bin/tectonic`），将 LaTeX 编译为 PDF 时可直接使用 Tectonic。\n' "${HOME}" >> "${MERGED_RULE}"
        target_rule="${MERGED_RULE}"
    fi
    ln -sf "${target_rule}" "${GLOBAL_CONFIG_RULE}"
    ln -sf "${target_rule}" "${HOME_GEMINI_RULE}"
    echo "[规则] 已挂载全局中文思考规范 (realpath 自动去重) -> ${target_rule}"
}

deploy_zh_bin() {
    local extra_arg="${1:-}"
    ensure_backup
    if [[ -n "${extra_arg}" ]]; then
        python3 "${SCRIPT_DIR}/patch_agy.py" --source "${AGY_BIN}" --backup "${ORIG_BIN}" --target "${ZH_BIN}" "${extra_arg}"
    else
        python3 "${SCRIPT_DIR}/patch_agy.py" --source "${AGY_BIN}" --backup "${ORIG_BIN}" --target "${ZH_BIN}"
    fi
    local tmp_bin="${AGY_BIN}.tmp.$$"
    cp -p "${ZH_BIN}" "${tmp_bin}"
    if [[ "$(uname -s)" == "Darwin" ]]; then
        codesign -f -s - "${tmp_bin}" >/dev/null 2>&1 || true
    fi
    mv -f "${tmp_bin}" "${AGY_BIN}"
    install_rules
    echo "[完成] 已激活中文增强版: ${AGY_BIN} ($("${AGY_BIN}" --version 2>/dev/null || echo 'OK'))"
}

restore_original() {
    if [[ -f "${ORIG_BIN}" ]]; then
        local tmp_bin="${AGY_BIN}.tmp.$$"
        cp -p "${ORIG_BIN}" "${tmp_bin}"
        if [[ "$(uname -s)" == "Darwin" ]]; then
            codesign -f -s - "${tmp_bin}" >/dev/null 2>&1 || true
        fi
        mv -f "${tmp_bin}" "${AGY_BIN}"
        echo "[还原] 已恢复原版二进制: ${AGY_BIN}"
    else
        echo "[提示] 未找到备份文件 ${ORIG_BIN}，无需恢复二进制"
    fi
    rm -f "${GLOBAL_CONFIG_RULE}" "${HOME_GEMINI_RULE}"
    if [[ -f "${BACKUP_RULE}" ]]; then
        cp -p "${BACKUP_RULE}" "${HOME_GEMINI_RULE}"
        echo "[还原] 已恢复原有规则至: ${HOME_GEMINI_RULE}"
    fi
    if [[ -f "${BACKUP_CONFIG_RULE}" ]]; then
        cp -p "${BACKUP_CONFIG_RULE}" "${GLOBAL_CONFIG_RULE}"
        echo "[还原] 已恢复原有规则至: ${GLOBAL_CONFIG_RULE}"
    fi
}

show_status() {
    echo "============================================================"
    echo "       Antigravity CLI 中文原生思考增强套件状态"
    echo "============================================================"
    if [[ -f "${AGY_BIN}" ]]; then
        local cur_sha
        cur_sha="$(calc_sha256 "${AGY_BIN}")"
        echo "当前 agy 路径  : ${AGY_BIN}"
        echo "当前 agy 版本  : $("${AGY_BIN}" --version 2>/dev/null || echo '未知')"
        echo "当前 SHA256    : ${cur_sha}"
        if [[ -f "${ORIG_BIN}" ]]; then
            local orig_sha
            orig_sha="$(calc_sha256 "${ORIG_BIN}")"
            if [[ "${cur_sha}" == "${orig_sha}" ]]; then
                echo "二进制补丁状态 : 隔离/原版模式 (系统 agy 未打补丁)"
            else
                echo "二进制补丁状态 : 已启用全局中文思考槽位合流与防截断补丁"
            fi
        fi
    fi
    if [[ -L "${GLOBAL_CONFIG_RULE}" || -f "${GLOBAL_CONFIG_RULE}" ]]; then
        echo "全局规则状态   : 已启用 (${GLOBAL_CONFIG_RULE})"
    else
        echo "全局规则状态   : 未启用"
    fi
    echo "============================================================"
}

case "${1:-status}" in
    enable|enable-global)
        deploy_zh_bin ""
        ;;
    enable-ui)
        deploy_zh_bin "--ui-zh"
        ;;
    apply-rules)
        install_rules
        ;;
    disable|restore)
        restore_original
        ;;
    status)
        show_status
        ;;
    *)
        usage
        exit 1
        ;;
esac
