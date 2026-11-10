#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Antigravity CLI 中文原生思考槽位合流与渲染补丁自动化验证脚本 (跨平台版)
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "scripts"))

from patch_agy import (  # noqa: E402
    DEFAULT_BACKUP,
    DEFAULT_TARGET,
    detect_binary_profile,
    sha256_file,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="校验 Antigravity 中文增强补丁与运行状态")
    parser.add_argument(
        "--binary",
        default="",
        help="指定待校验的二进制路径（默认优先校验已生效的系统 agy，若处于隔离模式则校验 ./bin/agy-zh）",
    )
    args = parser.parse_args()

    print("========================================================")
    print("  Antigravity CLI 中文原生思考与渲染补丁全面核验")
    print("========================================================")

    sys_agy = shutil.which("agy") or os.path.expanduser("~/.local/bin/agy")
    target_bin = args.binary
    if not target_bin:
        if os.path.exists(DEFAULT_TARGET) and os.path.exists(DEFAULT_BACKUP) and os.path.exists(sys_agy):
            # 若系统 agy 仍等于备份原版，说明用户在运行隔离模式 (--isolated)，此时校验 DEFAULT_TARGET
            if sha256_file(sys_agy) == sha256_file(DEFAULT_BACKUP):
                target_bin = DEFAULT_TARGET
            else:
                target_bin = sys_agy
        elif os.path.exists(sys_agy):
            target_bin = sys_agy
        else:
            target_bin = DEFAULT_TARGET

    if not os.path.exists(target_bin):
        print(f"[失败] 未找到待校验二进制文件: {target_bin}")
        sys.exit(1)

    with open(target_bin, "rb") as f:
        data = f.read()

    profile_name, patches = detect_binary_profile(data[:16], ui_zh=False)
    print(f"  [INFO] 校验目标路径: {target_bin}")
    print(f"  [INFO] 识别平台架构: {profile_name}")

    all_ok = True
    for idx, p in enumerate(patches, 1):
        actual = data[p.offset : p.offset + len(p.patched)]
        ok = actual == p.patched
        all_ok = all_ok and ok
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] #{idx:02d} 0x{p.offset:08x} ({len(p.patched):3d}B) | {p.name}")

    if platform.system() == "Darwin":
        sig_res = subprocess.run(["codesign", "-v", target_bin], capture_output=True, text=True)
        sig_ok = sig_res.returncode == 0
        all_ok = all_ok and sig_ok
        print(f"  [{'PASS' if sig_ok else 'FAIL'}] macOS ARM64 Mach-O 代码签名校验 (codesign -v)")

    ver_res = subprocess.run([target_bin, "--version"], capture_output=True, text=True)
    ver_ok = ver_res.returncode == 0 and len(ver_res.stdout.strip()) > 0
    all_ok = all_ok and ver_ok
    print(f"  [{'PASS' if ver_ok else 'FAIL'}] CLI 启动与版本健康检查: {ver_res.stdout.strip()}")

    rule_paths = [
        os.path.expanduser("~/.gemini/config/GEMINI.md"),
        os.path.expanduser("~/.gemini/GEMINI.md"),
    ]
    for rp in rule_paths:
        if os.path.exists(rp) and os.path.getsize(rp) > 100:
            print(f"  [PASS] 全局中文思考规则已就绪: {rp}")
        else:
            print(f"  [INFO] 全局中文思考规则尚未挂载 (隔离模式可选): {rp}")

    if os.path.exists(DEFAULT_BACKUP):
        print(f"  [INFO] 原版备份 SHA256: {sha256_file(DEFAULT_BACKUP)}")
    print(f"  [INFO] 校验目标 SHA256: {sha256_file(target_bin)}")

    if not all_ok:
        sys.exit(2)
    print("\n[全部通过] Antigravity 中文原生思考增强补丁已 100% 正常生效！")


if __name__ == "__main__":
    main()
