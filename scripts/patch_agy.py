#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Antigravity CLI (agy v1.5.0) 中文增强与渲染修复二进制补丁引擎
安全隔离原则：
- 默认读取本机 ~/.local/bin/agy 作为只读源文件；
- 在隔离目录 ~/projects/antigravity-chinese/bin/ 下生成备份 agy.orig 与中文增强版 agy-zh；
- 绝不修改用户正在使用的 ~/.local/bin/agy。

核心二进制修复模块：
1. [代码补丁 @ 0x9aaeb20 (23B)] Glamour Markdown 自动折行预留 4 列安全右边距，根治中文引用块与弯引号右侧吞字
（注：界面所有标签、Ran (command) 括号内的原始命令、以及 Thought for xx s (sentence) 括号结构均 100% 保持官方原生专业样式）
"""

import argparse
import hashlib
import os
import shutil
import stat
import sys
from dataclasses import dataclass
from typing import List

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SOURCE = shutil.which("agy") or os.path.expanduser("~/.local/bin/agy")
DEFAULT_BACKUP = os.path.join(PROJECT_ROOT, "bin", "agy.orig")
DEFAULT_TARGET = os.path.join(PROJECT_ROOT, "bin", "agy-zh")


@dataclass
class BinaryPatch:
    name: str
    offset: int
    original: bytes
    patched: bytes
    description: str


def get_patches() -> List[BinaryPatch]:
    patches: List[BinaryPatch] = []

    # =========================================================================
    # 1. Markdown 自动折行预留 4 列安全右边距 (0x9aaeb20, 23 字节)
    # =========================================================================
    patches.append(BinaryPatch(
        name="markdown_safe_wordwrap_margin",
        offset=0x9aaeb20,
        original=bytes.fromhex("488b4a084889482031c031dbc3cccccccccccccccccccc"),
        patched=bytes.fromhex("488b4a084883f9147e044883e9044889482031c031dbc3"),
        description="为 Glamour Markdown 折行预留 4 列右边距，根治中文引用块与弯引号右侧吞字",
    ))

    for p in patches:
        assert len(p.original) == len(p.patched), f"Patch {p.name} length mismatch!"
    return patches


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def apply_patches(source_path: str, backup_path: str, target_path: str, dry_run: bool = False) -> None:
    if not os.path.exists(source_path):
        print(f"[错误] 未找到源二进制文件: {source_path}", file=sys.stderr)
        sys.exit(1)

    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    if not os.path.exists(backup_path) and not dry_run:
        print(f"[备份] 正在将原版二进制安全备份至隔离目录: {backup_path}")
        shutil.copy2(source_path, backup_path)

    with open(source_path, "rb") as f:
        data = bytearray(f.read())

    patches = get_patches()
    print(f"[检查] 共加载 {len(patches)} 项补丁位点，开始逐项校验字节特征...")

    for idx, p in enumerate(patches, 1):
        actual = bytes(data[p.offset : p.offset + len(p.original)])
        if actual == p.original:
            status = "匹配原版字节 (待打补丁)"
        elif actual == p.patched:
            status = "已处于补丁状态"
        else:
            print(
                f"[致命错误] 补丁 #{idx} ({p.name} @ 0x{p.offset:x}) 字节校验不匹配！\n"
                f"  期望原版: {p.original.hex()}\n"
                f"  实际读取: {actual.hex()}",
                file=sys.stderr,
            )
            sys.exit(2)
        print(f"  [{idx:02d}/{len(patches):02d}] 0x{p.offset:08x} ({len(p.original):2d}B) | {p.name:<30} | {status}")
        print(f"          说明: {p.description}")
        data[p.offset : p.offset + len(p.patched)] = p.patched

    if dry_run:
        print("\n[干跑完成] 所有位点校验 100% 通过（未写入文件）。")
        return

    tmp_path = f"{target_path}.tmp.{os.getpid()}"
    with open(tmp_path, "wb") as f:
        f.write(data)
    st = os.stat(source_path)
    os.chmod(tmp_path, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    os.replace(tmp_path, target_path)

    orig_hash = sha256_file(source_path)
    new_hash = sha256_file(target_path)
    print("\n[成功] 隔离版中文增强二进制已生成！")
    print(f"  原版路径 (未改动): {source_path}")
    print(f"  原版 SHA256      : {orig_hash}")
    print(f"  隔离备份路径     : {backup_path}")
    print(f"  增强版输出路径   : {target_path}")
    print(f"  增强版 SHA256    : {new_hash}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Antigravity CLI 中文增强补丁构建脚本（安全隔离版）")
    parser.add_argument("--source", default=DEFAULT_SOURCE, help="只读原版 agy 路径")
    parser.add_argument("--backup", default=DEFAULT_BACKUP, help="隔离目录中的原版备份路径")
    parser.add_argument("--target", default=DEFAULT_TARGET, help="隔离目录中的输出路径 (agy-zh)")
    parser.add_argument("--dry-run", action="store_true", help="仅校验偏移与字节特征，不写入文件")
    args = parser.parse_args()
    apply_patches(args.source, args.backup, args.target, args.dry_run)


if __name__ == "__main__":
    main()
