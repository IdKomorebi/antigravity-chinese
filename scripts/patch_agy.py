#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Antigravity CLI 中文原生思考槽位合流与渲染修复补丁引擎 (v2 多平台自适应版)

支持目标：
- macOS Apple Silicon (arm64 Mach-O, agy v1.5.4)：
  10 处核心二进制补丁（原生思考槽位中文合流 + 流式防闪烁/防吞没 + 解除 '...' 截断 + Glamour 右边距防吞字）
  + 可选 5 处 UI 状态词条汉化 (--ui-zh)，并自动执行 codesign -f -s - 重签名。
- Linux x86_64 (ELF, agy v1.5.0)：
  向下兼容原 main 分支的 Glamour Markdown 安全右边距补丁。
"""

import argparse
import hashlib
import os
import platform
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass
from typing import List, Tuple

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SOURCE = shutil.which("agy") or os.path.expanduser("~/.local/bin/agy")
DEFAULT_BACKUP = os.path.join(PROJECT_ROOT, "bin", "agy.orig")
DEFAULT_TARGET = os.path.join(PROJECT_ROOT, "bin", "agy-zh")

MACHO_MAGIC_64_LE = bytes.fromhex("cffaedfe")
ELF_MAGIC = b"\x7fELF"


@dataclass
class BinaryPatch:
    name: str
    offset: int
    original: bytes
    patched: bytes
    description: str


def get_macos_arm64_v154_core_patches() -> List[BinaryPatch]:
    patches: List[BinaryPatch] = [
        # 1. Glamour Markdown 折行预留 4 列安全右边距 (WithWordWrap.func1 @ 0x02bb0560, 32B)
        BinaryPatch(
            name="markdown_safe_wordwrap_margin",
            offset=0x02BB0560,
            original=bytes.fromhex(
                "420740f9021000f9e0031faae1031faac0035fd6000000000000000000000000"
            ),
            patched=bytes.fromhex(
                "420740f95f5000f14d000054421000d1021000f9e0031faae1031faac0035fd6"
            ),
            description="为 Glamour Markdown 自动折行预留 4 列安全右边距，根治中文引用块与右侧边缘吞字",
        ),
        # 2a. 原生思考槽位中文思维链合流引擎 (stepContent @ 0x02c78624, 100B)
        BinaryPatch(
            name="native_thought_slot_zh_fusion",
            offset=0x02C78624,
            original=bytes.fromhex(
                "270100b4e92040f9890000b4e9a843a91f2003d506000014e9a842a91f2003d5"
                "03000014ea031faae9031faa1f2003d5000100b40bb045a97f0108eb40000054"
                "ec031faa61000054880140f902000014e8031faa680000b4080940f902000014"
                "e8031faa"
            ),
            patched=bytes.fromhex(
                "470200b4e9a840a9e8030aaa6a0100b45f010af128010054eb5040f9ab0000b5"
                "c00000b40b0c40b97f0d007160000054080080920c000014e9a843a94a0100b5"
                "e9a842a908000014e8031faae9031faaea031faa1f2003d51f2003d51f2003d5"
                "1f2003d5"
            ),
            description="在流式阶段及工具调用步骤将主模型生成的中文思考摘要直接注入 ▸ Thought 槽位，杜绝先吐在正文再消失",
        ),
        # 2b. 折叠思考块第二行摘要渲染修复 (stepContent @ 0x02c78fe8, 12B)
        BinaryPatch(
            name="step_content_render_fused_snippet",
            offset=0x02C78FE8,
            original=bytes.fromhex("fb234091620b68f9020300b4"),
            patched=bytes.fromhex("620b68f95f0000f10d030054"),
            description="将 cbz x2, 0x102c79050 扩展为 cmp x2, #0; b.le 0x102c79050，确保 x8=-1 合流态正常渲染 ▸ Thought 第二行中文摘要",
        ),
        # 2c. low 详细度下保留已合流思考块 (stepContent @ 0x02c78b18, 4B)
        BinaryPatch(
            name="step_content_low_verbosity_keep_thought",
            offset=0x02C78B18,
            original=bytes.fromhex("080100b4"),
            patched=bytes.fromhex("08000014"),
            description="确保在 verbosity=low 模式下已合流中文思考块同样正常渲染而不被跳过",
        ),
        # 3a. 流式思考分支已合流正文抑制器 (stepContent @ 0x02c78a94, 8B)
        BinaryPatch(
            name="step_content_live_suppress_dup_body",
            offset=0x02C78A94,
            original=bytes.fromhex("fb234091680b68f9"),
            patched=bytes.fromhex("680b68f908fda88a"),
            description="流式思考渲染后通过 bic x8, x8, x8, asr #63 自动抑制下方重复渲染已合流的中文思考",
        ),
        # 3b. 完成态思考分支已合流正文抑制器 (stepContent @ 0x02c79b70, 8B)
        BinaryPatch(
            name="step_content_done_suppress_dup_body",
            offset=0x02C79B70,
            original=bytes.fromhex("fb234091680b68f9"),
            patched=bytes.fromhex("680b68f908fda88a"),
            description="完成态思考渲染后通过 bic x8, x8, x8, asr #63 自动抑制下方重复渲染已合流的中文思考",
        ),
        # 4a. 折叠思考块保留完整段落 (collapsedThinkingSnippet @ 0x02c7558c, 4B)
        BinaryPatch(
            name="collapsed_thinking_keep_paragraphs",
            offset=0x02C7558C,
            original=bytes.fromhex("a001f8b7"),
            patched=bytes.fromhex("0d000014"),
            description="禁止 collapsedThinkingSnippet 仅截取末段文本，完整保留全段中文思考",
        ),
        # 4b. 折叠思考块取消 fitDetailText 单行省略号截断 (collapsedThinkingSnippet @ 0x02c755d4, 4B)
        BinaryPatch(
            name="collapsed_thinking_no_ellipsis_trunc",
            offset=0x02C755D4,
            original=bytes.fromhex("07baff97"),
            patched=bytes.fromhex("1f2003d5"),
            description="移除 collapsedThinkingSnippet 中的 fitDetailText 截断调用，按终端宽度自动折行",
        ),
        # 5a. 里程碑思考摘要反截断 #1 (semanticMilestoneLines @ 0x02c64c80, 4B)
        BinaryPatch(
            name="milestone_thinking_no_trunc_1",
            offset=0x02C64C80,
            original=bytes.fromhex("5cfcff97"),
            patched=bytes.fromhex("1f2003d5"),
            description="移除 semanticMilestoneLines 分支 1 的 fitDetailText 单行截断",
        ),
        # 5b. 里程碑思考摘要反截断 #2 (semanticMilestoneLines @ 0x02c64e58, 4B)
        BinaryPatch(
            name="milestone_thinking_no_trunc_2",
            offset=0x02C64E58,
            original=bytes.fromhex("e6fbff97"),
            patched=bytes.fromhex("1f2003d5"),
            description="移除 semanticMilestoneLines 分支 2 的 fitDetailText 单行截断",
        ),
    ]
    for p in patches:
        assert len(p.original) == len(p.patched), f"Patch {p.name} length mismatch!"
    return patches


def get_macos_arm64_v154_ui_patches() -> List[BinaryPatch]:
    """可选的 .rodata 界面标签等长中文替换（仅在 --ui-zh 模式下启用）"""
    raw_items = [
        (
            "ui_thought_for_tokens",
            0x03997802,
            b"Thought for %s, %s tokens",
            "思考耗时 %s · %s 词元".encode("utf-8").ljust(25, b" "),
            "将 'Thought for %s, %s tokens' 汉化为 '思考耗时 %s · %s 词元'",
        ),
        (
            "ui_thought_for_s",
            0x038CB971,
            b"Thought for %s",
            "思考耗时 %s".encode("utf-8").ljust(14, b" "),
            "将 'Thought for %s' 汉化为 '思考耗时 %s'",
        ),
        (
            "ui_thought_process",
            0x038E14E2,
            b"Thought Process",
            "思考推理过程   ".encode("utf-8"),
            "将 'Thought Process' 汉化为 '思考推理过程'",
        ),
        (
            "ui_ctrl_o_expand",
            0x038F660B,
            b"ctrl+o to expand",
            "ctrl+o 展开详情 ".encode("utf-8"),
            "将 'ctrl+o to expand' 汉化为 'ctrl+o 展开详情'",
        ),
        (
            "ui_ctrl_o_collapse",
            0x0391D745,
            b"ctrl+o to collapse",
            "ctrl+o 折叠收起   ".encode("utf-8"),
            "将 'ctrl+o to collapse' 汉化为 'ctrl+o 折叠收起'",
        ),
    ]
    patches: List[BinaryPatch] = []
    for name, off, orig, rep, desc in raw_items:
        assert len(orig) == len(rep), f"UI patch {name} byte length mismatch"
        patches.append(BinaryPatch(name=name, offset=off, original=orig, patched=rep, description=desc))
    return patches


def get_linux_x86_64_v150_patches() -> List[BinaryPatch]:
    """向下兼容原 main 分支的 Linux x86_64 (agy v1.5.0) 补丁位点"""
    return [
        BinaryPatch(
            name="markdown_safe_wordwrap_margin",
            offset=0x09AAEB20,
            original=bytes.fromhex("488b4a084889482031c031dbc3cccccccccccccccccccc"),
            patched=bytes.fromhex("488b4a084883f9147e044883e9044889482031c031dbc3"),
            description="为 Glamour Markdown 折行预留 4 列右边距，根治中文引用块与弯引号右侧吞字",
        )
    ]


def detect_binary_profile(data: bytes, ui_zh: bool = False) -> Tuple[str, List[BinaryPatch]]:
    if data[:4] == MACHO_MAGIC_64_LE:
        patches = get_macos_arm64_v154_core_patches()
        if ui_zh:
            patches.extend(get_macos_arm64_v154_ui_patches())
        return "macOS ARM64 Mach-O (agy v1.5.4)", patches
    if data[:4] == ELF_MAGIC:
        return "Linux x86_64 ELF (agy v1.5.0)", get_linux_x86_64_v150_patches()
    raise RuntimeError(f"无法识别的可执行文件头魔数: {data[:4].hex()}")


# 保持向后兼容导出的辅助函数名
def get_core_patches() -> List[BinaryPatch]:
    return get_macos_arm64_v154_core_patches()


def get_patches(binary_path: str = DEFAULT_SOURCE) -> List[BinaryPatch]:
    if os.path.exists(binary_path):
        with open(binary_path, "rb") as f:
            head = f.read(16)
        _, patches = detect_binary_profile(head, ui_zh=False)
        return patches
    return get_macos_arm64_v154_core_patches()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def get_cli_version(path: str) -> str:
    try:
        res = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        pass
    return ""


def codesign_binary(path: str) -> None:
    if platform.system() == "Darwin":
        subprocess.run(["codesign", "-f", "-s", "-", path], check=True)


def apply_patches(
    source_path: str,
    backup_path: str,
    target_path: str,
    ui_zh: bool = False,
    dry_run: bool = False,
) -> None:
    if not os.path.exists(source_path):
        print(f"[错误] 未找到源二进制文件: {source_path}", file=sys.stderr)
        sys.exit(1)

    os.makedirs(os.path.dirname(backup_path), exist_ok=True)
    os.makedirs(os.path.dirname(target_path), exist_ok=True)

    # 检测 agy 是否因官方升级 (agy update) 发生了版本变更，避免旧备份覆盖新版本
    if os.path.exists(backup_path) and os.path.abspath(source_path) != os.path.abspath(backup_path):
        src_ver = get_cli_version(source_path)
        bak_ver = get_cli_version(backup_path)
        if src_ver and bak_ver and src_ver != bak_ver:
            print(
                f"[警告] 检测到系统 agy 版本 ({src_ver}) 与现有备份 ({bak_ver}) 不一致！\n"
                f"       正在更新备份 {backup_path} 以对齐当前版本..."
            )
            if not dry_run:
                shutil.copy2(source_path, backup_path)

    if not os.path.exists(backup_path) and not dry_run:
        print(f"[备份] 正在将原版二进制安全备份至: {backup_path}")
        shutil.copy2(source_path, backup_path)

    base_source = backup_path if os.path.exists(backup_path) else source_path
    with open(base_source, "rb") as f:
        data = bytearray(f.read())

    profile_name, patches = detect_binary_profile(bytes(data[:16]), ui_zh=ui_zh)
    print(f"[识别] 目标平台架构: {profile_name}")
    print(f"[检查] 基准二进制  : {base_source}")
    print(f"[检查] 共加载 {len(patches)} 项补丁位点，开始逐项校验字节特征...")

    for idx, p in enumerate(patches, 1):
        actual = bytes(data[p.offset : p.offset + len(p.original)])
        if actual == p.original:
            status = "匹配原版字节 -> 应用补丁"
        elif actual == p.patched:
            status = "已处于补丁状态"
        else:
            print(
                f"[致命错误] 补丁 #{idx} ({p.name} @ 0x{p.offset:08x}) 字节校验不匹配！\n"
                f"  可能原因: 当前 agy 版本已升级，偏移发生变动，已安全中止写入。\n"
                f"  期望原版: {p.original.hex()}\n"
                f"  实际读取: {actual.hex()}",
                file=sys.stderr,
            )
            sys.exit(2)
        print(f"  [{idx:02d}/{len(patches):02d}] 0x{p.offset:08x} ({len(p.original):3d}B) | {p.name:<38} | {status}")
        print(f"          说明: {p.description}")
        data[p.offset : p.offset + len(p.patched)] = p.patched

    if dry_run:
        print("\n[干跑完成] 所有位点校验 100% 通过（未写入文件）。")
        return

    tmp_path = f"{target_path}.tmp.{os.getpid()}"
    with open(tmp_path, "wb") as f:
        f.write(data)
    st = os.stat(base_source)
    os.chmod(tmp_path, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    codesign_binary(tmp_path)
    os.replace(tmp_path, target_path)

    orig_hash = sha256_file(base_source)
    new_hash = sha256_file(target_path)
    print("\n[成功] 中文增强版二进制已生成！")
    print(f"  基准原版路径   : {base_source}")
    print(f"  基准原版 SHA256: {orig_hash}")
    print(f"  增强版输出路径 : {target_path}")
    print(f"  增强版 SHA256  : {new_hash}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Antigravity CLI 中文原生思考合流与渲染修复补丁构建脚本")
    parser.add_argument("--source", default=DEFAULT_SOURCE, help="原版 agy 路径")
    parser.add_argument("--backup", default=DEFAULT_BACKUP, help="隔离目录中的原版备份路径 (agy.orig)")
    parser.add_argument("--target", default=DEFAULT_TARGET, help="增强版输出路径 (agy-zh)")
    parser.add_argument("--ui-zh", action="store_true", help="同时汉化 Thought for / ctrl+o 等 UI 状态标签 (macOS v1.5.4)")
    parser.add_argument("--dry-run", action="store_true", help="仅校验偏移与字节特征，不写入文件")
    args = parser.parse_args()
    apply_patches(args.source, args.backup, args.target, args.ui_zh, args.dry_run)


if __name__ == "__main__":
    main()
