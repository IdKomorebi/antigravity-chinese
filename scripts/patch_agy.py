#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Antigravity CLI 原生思考槽位中文合流与渲染修复补丁引擎

支持能力：
- macOS Apple Silicon (arm64 Mach-O, agy v1.5.4+)：
  10 处核心二进制补丁（原生思考槽位中文合流 + 流式防闪烁/防吞没 + 解除 '...' 截断 + Glamour 右边距防吞字）
  + 可选 5 处 UI 状态词条汉化 (--ui-zh)，并自动执行 codesign -f -s - 重签名。
- Linux x86_64 (ELF, agy v1.5.9 / v1.5.11+)：
  10 处核心二进制补丁（原生思考槽位中文合流 + 流式/完成态防重复渲染 + 解除 '...' 截断 + Glamour 右边距防吞字）
  + 可选 5 处 UI 状态词条汉化 (--ui-zh)。
- 跨版本自适应重定位：
  当 agy 自动升级至新小版本时，自动解析二进制内置的 Go 1.22+ .gopclntab 符号表并校验函数内唯一指令特征完成无感适配。
"""

import argparse
import hashlib
import os
import platform
import shutil
import stat
import struct
import subprocess
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SOURCE = shutil.which("agy") or os.path.expanduser("~/.local/bin/agy")
DEFAULT_BACKUP = os.path.join(PROJECT_ROOT, "bin", "agy.orig")
DEFAULT_TARGET = os.path.join(PROJECT_ROOT, "bin", "agy-zh")

MACHO_MAGIC_64_LE = bytes.fromhex("cffaedfe")
ELF_MAGIC = b"\x7fELF"
PE_MAGIC = b"MZ"


@dataclass
class BinaryPatch:
    name: str
    offset: int
    original: bytes
    patched: bytes
    description: str


# ============================================================================
# 1. 已知版本精确静态配置表 (Fast Path)
# ============================================================================


def get_macos_arm64_v154_core_patches() -> List[BinaryPatch]:
    """macOS Apple Silicon (agy v1.5.4) 10 处原生思考槽位中文合流与反截断核心补丁"""
    patches: List[BinaryPatch] = [
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
        BinaryPatch(
            name="step_content_render_fused_snippet",
            offset=0x02C78FE8,
            original=bytes.fromhex("fb234091620b68f9020300b4"),
            patched=bytes.fromhex("620b68f95f0000f10d030054"),
            description="将 cbz x2, 0x102c79050 扩展为 cmp x2, #0; b.le 0x102c79050，确保 x8=-1 合流态正常渲染 ▸ Thought 第二行中文摘要",
        ),
        BinaryPatch(
            name="step_content_low_verbosity_keep_thought",
            offset=0x02C78B18,
            original=bytes.fromhex("080100b4"),
            patched=bytes.fromhex("08000014"),
            description="确保在 verbosity=low 模式下已合流中文思考块同样正常渲染而不被跳过",
        ),
        BinaryPatch(
            name="step_content_live_suppress_dup_body",
            offset=0x02C78A94,
            original=bytes.fromhex("fb234091680b68f9"),
            patched=bytes.fromhex("680b68f908fda88a"),
            description="流式思考渲染后通过 bic x8, x8, x8, asr #63 自动抑制下方重复渲染已合流的中文思考",
        ),
        BinaryPatch(
            name="step_content_done_suppress_dup_body",
            offset=0x02C79B70,
            original=bytes.fromhex("fb234091680b68f9"),
            patched=bytes.fromhex("680b68f908fda88a"),
            description="完成态思考渲染后通过 bic x8, x8, x8, asr #63 自动抑制下方重复渲染已合流的中文思考",
        ),
        BinaryPatch(
            name="collapsed_thinking_keep_paragraphs",
            offset=0x02C7558C,
            original=bytes.fromhex("a001f8b7"),
            patched=bytes.fromhex("0d000014"),
            description="禁止 collapsedThinkingSnippet 仅截取末段文本，完整保留全段中文思考",
        ),
        BinaryPatch(
            name="collapsed_thinking_no_ellipsis_trunc",
            offset=0x02C755D4,
            original=bytes.fromhex("07baff97"),
            patched=bytes.fromhex("1f2003d5"),
            description="移除 collapsedThinkingSnippet 中的 fitDetailText 截断调用，按终端宽度自动折行",
        ),
        BinaryPatch(
            name="milestone_thinking_no_trunc_1",
            offset=0x02C64C80,
            original=bytes.fromhex("5cfcff97"),
            patched=bytes.fromhex("1f2003d5"),
            description="移除 semanticMilestoneLines 分支 1 的 fitDetailText 单行截断",
        ),
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


def _build_ui_patches(offsets: Tuple[int, int, int, int, int]) -> List[BinaryPatch]:
    o1, o2, o3, o4, o5 = offsets
    raw_items = [
        (
            "ui_thought_for_tokens",
            o1,
            b"Thought for %s, %s tokens",
            "思考耗时 %s, %s词元".encode("utf-8"),
            "将 'Thought for %s, %s tokens' 汉化为 '思考耗时 %s, %s词元'",
        ),
        (
            "ui_thought_for_s",
            o2,
            b"Thought for %s",
            "思考耗时%s".encode("utf-8"),
            "将 'Thought for %s' 汉化为 '思考耗时%s'",
        ),
        (
            "ui_thought_process",
            o3,
            b"Thought Process",
            "思考与推理".encode("utf-8"),
            "将 'Thought Process' 汉化为 '思考与推理'",
        ),
        (
            "ui_ctrl_o_expand",
            o4,
            b"ctrl+o to expand",
            "按ctrl+o 展开".encode("utf-8"),
            "将 'ctrl+o to expand' 汉化为 '按ctrl+o 展开'",
        ),
        (
            "ui_ctrl_o_collapse",
            o5,
            b"ctrl+o to collapse",
            "按ctrl+o可折叠".encode("utf-8"),
            "将 'ctrl+o to collapse' 汉化为 '按ctrl+o可折叠'",
        ),
    ]
    patches: List[BinaryPatch] = []
    for name, off, orig, rep, desc in raw_items:
        assert len(orig) == len(rep), f"UI patch {name} byte length mismatch"
        patches.append(BinaryPatch(name=name, offset=off, original=orig, patched=rep, description=desc))
    return patches


def get_macos_arm64_v154_ui_patches() -> List[BinaryPatch]:
    return _build_ui_patches((0x03997802, 0x038CB971, 0x038E14E2, 0x038F660B, 0x0391D745))


def _build_linux_x86_64_core_patches(
    off_wrap: int,
    off_fusion: int,
    off_snippet: int,
    off_low: int,
    off_suppress: int,
    off_keep_para: int,
    call_collapsed: Tuple[int, str],
    call_live: Tuple[int, str],
    call_ms1: Tuple[int, str],
    call_ms2: Tuple[int, str],
) -> List[BinaryPatch]:
    patches: List[BinaryPatch] = [
        BinaryPatch(
            name="markdown_safe_wordwrap_margin",
            offset=off_wrap,
            original=bytes.fromhex("488b4a084889482031c031dbc3cccccccccccccccccccc"),
            patched=bytes.fromhex("488b4a084883f9147e044883e9044889482031c031dbc3"),
            description="为 Glamour Markdown 自动折行预留 4 列安全右边距，根治中文引用块与右侧边缘吞字",
        ),
        BinaryPatch(
            name="native_thought_slot_zh_fusion",
            offset=off_fusion,
            original=bytes.fromhex(
                "4885d2742348837a4000740e904c8b5a384c8b62404885c0eb1d904c8b5a284c"
                "8b62304885c0eb0f4885c041bc0000000041bb0000000074194c39505875064c"
                "8b5060eb0641ba0000000075054d8b12eb034531d24d85d274084d8b52106690"
                "eb034531d2"
            ),
            patched=bytes.fromhex(
                "4885d2744e4c8b5a084c8b62104d89e24d85e47e274981fc800200007f1e4883"
                "baa000000000750b4885c0740f83780c03740949c7c2ffffffffeb204c8b5a38"
                "4c8b62404d85e475134c8b5a284c8b6230eb094531d24531db4531e490909090"
                "9090909090"
            ),
            description="在流式阶段及工具调用步骤将主模型生成的中文思考摘要直接注入 ▸ Thought 槽位，杜绝先吐在正文再消失",
        ),
        BinaryPatch(
            name="step_content_render_fused_snippet",
            offset=off_snippet,
            original=bytes.fromhex("745c"),
            patched=bytes.fromhex("7e5c"),
            description="将 je 升级为 jle，确保 %r10=-1 合流态正常渲染 ▸ Thought 第二行中文摘要",
        ),
        BinaryPatch(
            name="step_content_low_verbosity_keep_thought",
            offset=off_low,
            original=bytes.fromhex("741e"),
            patched=bytes.fromhex("7e1e"),
            description="将 verbosity=low 分支中的 je 升级为 jle，确保已合流中文思考块同样正常渲染而不被跳过",
        ),
        BinaryPatch(
            name="step_content_suppress_dup_body",
            offset=off_suppress,
            original=bytes.fromhex("0f844d020000"),
            patched=bytes.fromhex("0f8e4d020000"),
            description="在流式与完成态汇聚闸门将 je 升级为 jle，自动抑制下方重复白字正文",
        ),
        BinaryPatch(
            name="collapsed_thinking_keep_paragraphs",
            offset=off_keep_para,
            original=bytes.fromhex("7c32"),
            patched=bytes.fromhex("eb32"),
            description="禁止 collapsedThinkingSnippet 仅截取末段文本，完整保留全段中文思考",
        ),
        BinaryPatch(
            name="collapsed_thinking_no_ellipsis_trunc",
            offset=call_collapsed[0],
            original=bytes.fromhex(call_collapsed[1]),
            patched=bytes.fromhex("0f1f440000"),
            description="移除 collapsedThinkingSnippet 中的 fitDetailText 截断调用，按终端宽度自动折行",
        ),
        BinaryPatch(
            name="live_thinking_no_ellipsis_trunc",
            offset=call_live[0],
            original=bytes.fromhex(call_live[1]),
            patched=bytes.fromhex("0f1f440000"),
            description="移除流式纯思考阶段 fitDetailText 单行截断调用，流式思考同样完整自动折行",
        ),
        BinaryPatch(
            name="milestone_thinking_no_trunc_1",
            offset=call_ms1[0],
            original=bytes.fromhex(call_ms1[1]),
            patched=bytes.fromhex("0f1f440000"),
            description="移除 semanticMilestoneLines 分支 1 的 fitDetailText 单行截断",
        ),
        BinaryPatch(
            name="milestone_thinking_no_trunc_2",
            offset=call_ms2[0],
            original=bytes.fromhex(call_ms2[1]),
            patched=bytes.fromhex("0f1f440000"),
            description="移除 semanticMilestoneLines 分支 2 的 fitDetailText 单行截断",
        ),
    ]
    for p in patches:
        assert len(p.original) == len(p.patched), f"Patch {p.name} length mismatch!"
    return patches


def get_linux_x86_64_v1511_core_patches() -> List[BinaryPatch]:
    """Linux x86_64 (agy v1.5.11) 10 处核心补丁"""
    return _build_linux_x86_64_core_patches(
        off_wrap=0x0A6EF5A0,
        off_fusion=0x0A7E7180,
        off_snippet=0x0A7E7E47,
        off_low=0x0A7E786E,
        off_suppress=0x0A7E8085,
        off_keep_para=0x0A7E36FC,
        call_collapsed=(0x0A7E374A, "e8b1aefeff"),
        call_live=(0x0A7E764F, "e8ac6ffeff"),
        call_ms1=(0x0A7CF658, "e8a3efffff"),
        call_ms2=(0x0A7CF879, "e882edffff"),
    )


def get_linux_x86_64_v1511_ui_patches() -> List[BinaryPatch]:
    return _build_ui_patches((0x064BCB4D, 0x063EB56D, 0x0640186F, 0x06416FC5, 0x0643F0A8))


def get_linux_x86_64_v159_core_patches() -> List[BinaryPatch]:
    """Linux x86_64 (agy v1.5.9) 10 处核心补丁"""
    return _build_linux_x86_64_core_patches(
        off_wrap=0x0A455F00,
        off_fusion=0x0A54BE00,
        off_snippet=0x0A54CAC7,
        off_low=0x0A54C4EE,
        off_suppress=0x0A54CD05,
        off_keep_para=0x0A5483DC,
        call_collapsed=(0x0A54842A, "e831b1feff"),
        call_live=(0x0A54C2CF, "e88c72feff"),
        call_ms1=(0x0A5345B8, "e8a3efffff"),
        call_ms2=(0x0A5347D9, "e882edffff"),
    )


def get_linux_x86_64_v159_ui_patches() -> List[BinaryPatch]:
    return _build_ui_patches((0x06365E00, 0x0629636E, 0x062AC343, 0x062C18FF, 0x062E950F))


# ============================================================================
# 2. Go 1.22+ .gopclntab 跨版本自适应重定位引擎 (Smart Relocation Fallback)
# ============================================================================

TARGET_SUFFIXES = (
    "/glamour.WithWordWrap.func1",
    "/render.stepContent",
    "/render.collapsedThinkingSnippet",
    "/render.semanticMilestoneLines",
    "/render.fitDetailText",
)


def _find_gopclntab_functions(data: bytes) -> Optional[Dict[str, Tuple[int, int]]]:
    """扫描 Go 1.22+ pcHeader (0xfffffff1)，返回目标函数的 (entry_off, size) 字典"""
    pos = 0
    gop_off = -1
    words = None
    while True:
        idx = data.find(b"\xf1\xff\xff\xff\x00\x00", pos)
        if idx < 0:
            break
        if idx + 72 <= len(data) and data[idx + 6] in (1, 2, 4) and data[idx + 7] == 8:
            cand = struct.unpack_from("<8Q", data, idx + 8)
            nfunc, nfiles, _, funcname_off, _, _, _, pcln_off = cand
            if 5000 < nfunc < 2000000 and 100 < nfiles < 500000 and idx + pcln_off + nfunc * 8 <= len(data):
                gop_off = idx
                words = cand
                break
        pos = idx + 1

    if gop_off < 0 or words is None:
        return None

    nfunc, _, _, funcname_off, _, _, _, pcln_off = words
    fn_base = gop_off + funcname_off
    ftab_base = gop_off + pcln_off
    found: Dict[str, Tuple[int, int]] = {}
    for i in range(nfunc):
        entry_off, info_off = struct.unpack_from("<II", data, ftab_base + i * 8)
        _, name_off = struct.unpack_from("<Ii", data, ftab_base + info_off)
        end = data.find(b"\x00", fn_base + name_off)
        if end < 0:
            continue
        fname = data[fn_base + name_off : end].decode("utf-8", "replace")
        for suf in TARGET_SUFFIXES:
            if fname.endswith(suf):
                next_entry_off = struct.unpack_from("<I", data, ftab_base + (i + 1) * 8)[0]
                found[suf] = (entry_off, next_entry_off - entry_off)
                break
        if len(found) == len(TARGET_SUFFIXES):
            break
    return found if len(found) == len(TARGET_SUFFIXES) else None


def _unique_find_either(buf: bytes, orig_pat: bytes, patched_pat: bytes) -> Optional[int]:
    hits = []
    for pat in (orig_pat, patched_pat):
        p = buf.find(pat)
        while p >= 0:
            if p not in hits:
                hits.append(p)
            p = buf.find(pat, p + 1)
    return hits[0] if len(hits) == 1 else None


def _auto_locate_linux_x86_64(data: bytes, ui_zh: bool = False) -> Optional[List[BinaryPatch]]:
    rel_funcs = _find_gopclntab_functions(data)
    if not rel_funcs:
        return None

    wrap_orig = bytes.fromhex("488b4a084889482031c031dbc3cccccccccccccccccccc")
    wrap_patched = bytes.fromhex("488b4a084883f9147e044883e9044889482031c031dbc3")
    wrap_pos = data.find(wrap_orig)
    if wrap_pos < 0:
        wrap_pos = data.find(wrap_patched)
    if wrap_pos < 0:
        return None

    text_base = wrap_pos - rel_funcs["/glamour.WithWordWrap.func1"][0]
    if text_base <= 0:
        return None

    sc_off = text_base + rel_funcs["/render.stepContent"][0]
    sc_sz = rel_funcs["/render.stepContent"][1]
    ct_off = text_base + rel_funcs["/render.collapsedThinkingSnippet"][0]
    ct_sz = rel_funcs["/render.collapsedThinkingSnippet"][1]
    ms_off = text_base + rel_funcs["/render.semanticMilestoneLines"][0]
    ms_sz = rel_funcs["/render.semanticMilestoneLines"][1]
    fit_off = text_base + rel_funcs["/render.fitDetailText"][0]

    sc_buf = bytes(data[sc_off : sc_off + sc_sz])
    ct_buf = bytes(data[ct_off : ct_off + ct_sz])

    fusion_orig = bytes.fromhex(
        "4885d2742348837a4000740e904c8b5a384c8b62404885c0eb1d904c8b5a284c"
        "8b62304885c0eb0f4885c041bc0000000041bb0000000074194c39505875064c"
        "8b5060eb0641ba0000000075054d8b12eb034531d24d85d274084d8b52106690"
        "eb034531d2"
    )
    fusion_patched = bytes.fromhex(
        "4885d2744e4c8b5a084c8b62104d89e24d85e47e274981fc800200007f1e4883"
        "baa000000000750b4885c0740f83780c03740949c7c2ffffffffeb204c8b5a38"
        "4c8b62404d85e475134c8b5a284c8b6230eb094531d24531db4531e490909090"
        "9090909090"
    )
    r_fusion = _unique_find_either(sc_buf, fusion_orig, fusion_patched)
    r_snippet = _unique_find_either(
        sc_buf,
        bytes.fromhex("4885c9745c31c0bb0100000031c989df"),
        bytes.fromhex("4885c97e5c31c0bb0100000031c989df"),
    )
    r_low = _unique_find_either(
        sc_buf,
        bytes.fromhex("41807d027775284d85d2741e"),
        bytes.fromhex("41807d027775284d85d27e1e"),
    )
    r_suppress = _unique_find_either(
        sc_buf,
        bytes.fromhex("4d85d26690eb034d85d20f844d020000"),
        bytes.fromhex("4d85d26690eb034d85d20f8e4d020000"),
    )
    r_para = _unique_find_either(
        ct_buf,
        bytes.fromhex("4885c07c32488d4802"),
        bytes.fromhex("4885c0eb32488d4802"),
    )
    if None in (r_fusion, r_snippet, r_low, r_suppress, r_para):
        return None

    def find_fit_calls(f_start: int, f_sz: int, expected: int) -> Optional[List[Tuple[int, str]]]:
        res: List[Tuple[int, str]] = []
        nop5 = b"\x0f\x1f\x44\x00\x00"
        for off in range(f_start, f_start + f_sz - 5):
            rel = fit_off - (off + 5)
            call_bytes = b"\xe8" + int(rel).to_bytes(4, "little", signed=True)
            cur = data[off : off + 5]
            if cur == call_bytes:
                res.append((off, call_bytes.hex()))
            elif cur == nop5 and (off + 5) % 16 != 0 and (
                data[off - 5 : off - 2] == b"\x48\x8b\x4c"
                or data[off - 8 : off - 4] in (b"\x48\x8b\x8c\x24", b"\x48\x8b\x84\x24")
                or data[off - 3 : off] == b"\x48\x89\xd1"
            ):
                res.append((off, call_bytes.hex()))
        return res if len(res) == expected else None

    c_ct = find_fit_calls(ct_off, ct_sz, 1)
    c_sc = find_fit_calls(sc_off, sc_sz, 1)
    c_ms = find_fit_calls(ms_off, ms_sz, 2)
    if not (c_ct and c_sc and c_ms):
        return None

    patches = _build_linux_x86_64_core_patches(
        off_wrap=wrap_pos,
        off_fusion=sc_off + r_fusion,
        off_snippet=sc_off + r_snippet + 3,
        off_low=sc_off + r_low + 10,
        off_suppress=sc_off + r_suppress + 10,
        off_keep_para=ct_off + r_para + 3,
        call_collapsed=c_ct[0],
        call_live=c_sc[0],
        call_ms1=c_ms[0],
        call_ms2=c_ms[1],
    )
    if ui_zh:
        ui_patches = _auto_locate_linux_ui(data, sc_off, sc_sz)
        if not ui_patches:
            return None
        patches.extend(ui_patches)
    return patches


def _auto_locate_linux_ui(data: bytes, sc_off: int, sc_sz: int) -> Optional[List[BinaryPatch]]:
    """通过 render 包内的 RIP-relative LEA 引用精确定位 5 处 UI 字符串"""
    r_start = max(0, sc_off - 0x30000)
    r_end = min(len(data), sc_off + sc_sz + 0x30000)
    targets = [
        (b"Thought for %s, %s tokens", "思考耗时 %s, %s词元".encode("utf-8")),
        (b"Thought for %s", "思考耗时%s".encode("utf-8")),
        (b"Thought Process", "思考与推理".encode("utf-8")),
        (b"ctrl+o to expand", "按ctrl+o 展开".encode("utf-8")),
        (b"ctrl+o to collapse", "按ctrl+o可折叠".encode("utf-8")),
    ]
    referenced = set()
    for off in range(r_start, r_end - 7):
        if data[off] in (0x48, 0x4C) and data[off + 1] == 0x8D and (data[off + 2] & 0xC7) == 0x05:
            disp = int.from_bytes(data[off + 3 : off + 7], "little", signed=True)
            referenced.add(off + 7 + disp)

    resolved: List[int] = []
    for orig_s, rep_s in targets:
        hit = -1
        for addr in sorted(referenced):
            if 0 <= addr <= len(data) - len(orig_s):
                seg = data[addr : addr + len(orig_s)]
                if seg in (orig_s, rep_s):
                    if orig_s == b"Thought for %s" and data[addr : addr + 16] == b"Thought for %s, ":
                        continue
                    hit = addr
                    break
        if hit < 0:
            return None
        resolved.append(hit)
    return _build_ui_patches((resolved[0], resolved[1], resolved[2], resolved[3], resolved[4]))


def _auto_locate_macos_arm64(data: bytes, ui_zh: bool = False) -> Optional[List[BinaryPatch]]:
    rel_funcs = _find_gopclntab_functions(data)
    if not rel_funcs:
        return None

    wrap_orig = bytes.fromhex("420740f9021000f9e0031faae1031faac0035fd6000000000000000000000000")
    wrap_patched = bytes.fromhex("420740f95f5000f14d000054421000d1021000f9e0031faae1031faac0035fd6")
    wrap_pos = data.find(wrap_orig)
    if wrap_pos < 0:
        wrap_pos = data.find(wrap_patched)
    if wrap_pos < 0:
        return None

    text_base = wrap_pos - rel_funcs["/glamour.WithWordWrap.func1"][0]
    if text_base <= 0:
        return None

    sc_off = text_base + rel_funcs["/render.stepContent"][0]
    sc_sz = rel_funcs["/render.stepContent"][1]
    ct_off = text_base + rel_funcs["/render.collapsedThinkingSnippet"][0]
    ct_sz = rel_funcs["/render.collapsedThinkingSnippet"][1]
    ms_off = text_base + rel_funcs["/render.semanticMilestoneLines"][0]
    ms_sz = rel_funcs["/render.semanticMilestoneLines"][1]
    fit_off = text_base + rel_funcs["/render.fitDetailText"][0]

    sc_buf = bytes(data[sc_off : sc_off + sc_sz])
    ct_buf = bytes(data[ct_off : ct_off + ct_sz])

    v154 = get_macos_arm64_v154_core_patches()
    r_fusion = _unique_find_either(sc_buf, v154[1].original, v154[1].patched)
    r_para = _unique_find_either(ct_buf, v154[6].original, v154[6].patched)
    if r_fusion is None or r_para is None:
        return None

    # 定位折叠块第二行摘要分支 (add x27, sp, ...; ldr x2, [x27, #imm]; cbz x2, +0x60)
    snip_hits = []
    for r in range(0, sc_sz - 12, 4):
        w0, w1, w2 = struct.unpack_from("<III", sc_buf, r)
        if (w0 & 0xFFC003FF) == 0x914003FB and (w1 & 0xFFC003FF) == 0xF9400362 and w2 == 0xB4000302:
            snip_hits.append((r, sc_buf[r : r + 12], struct.pack("<III", w1, 0xF100005F, 0x5400030D), w0, w1 & 0xFFC003E0))
        elif (w0 & 0xFFC003FF) == 0xF9400362 and w1 == 0xF100005F and w2 == 0x5400030D:
            # 已打补丁态：从函数内相邻 add x27, sp 指令还原原始首字
            add_x27 = 0x914023FB
            for k in range(0, sc_sz - 4, 4):
                wk = struct.unpack_from("<I", sc_buf, k)[0]
                if (wk & 0xFFC003FF) == 0x914003FB:
                    add_x27 = wk
                    break
            orig12 = struct.pack("<III", add_x27, w0, 0xB4000302)
            snip_hits.append((r, orig12, sc_buf[r : r + 12], add_x27, w0 & 0xFFC003E0))
    if len(snip_hits) != 1:
        return None
    r_snip, snip_orig, snip_pat, add_x27_ins, ldr_imm_mask = snip_hits[0]
    ldr_x8_ins = ldr_imm_mask | 8

    # 定位流式与完成态两处重复正文抑制点 (add x27, sp, ...; ldr x8, [x27, #imm])
    sup_hits = []
    for r in range(0, sc_sz - 8, 4):
        w0, w1 = struct.unpack_from("<II", sc_buf, r)
        if w0 == add_x27_ins and w1 == ldr_x8_ins:
            sup_hits.append((r, struct.pack("<II", add_x27_ins, ldr_x8_ins), struct.pack("<II", ldr_x8_ins, 0x8AA8FD08)))
        elif w0 == ldr_x8_ins and w1 == 0x8AA8FD08:
            sup_hits.append((r, struct.pack("<II", add_x27_ins, ldr_x8_ins), struct.pack("<II", ldr_x8_ins, 0x8AA8FD08)))
    if len(sup_hits) != 2:
        return None

    # 定位 verbosity == "low" 分支中的 cbz x8, +0x20 (紧跟在第一处 suppress 之后 0x100 字节窗口内)
    low_start = sup_hits[0][0]
    low_window = sc_buf[low_start : min(sc_sz, low_start + 0x120)]
    r_low_rel = _unique_find_either(low_window, bytes.fromhex("080100b4"), bytes.fromhex("08000014"))
    if r_low_rel is None:
        return None
    r_low = low_start + r_low_rel

    def find_arm64_bl(f_start: int, f_sz: int, expected: int) -> Optional[List[Tuple[int, bytes]]]:
        res: List[Tuple[int, bytes]] = []
        nop4 = bytes.fromhex("1f2003d5")
        for off in range(f_start, f_start + f_sz, 4):
            imm26 = ((fit_off - off) >> 2) & 0x03FFFFFF
            bl_bytes = struct.pack("<I", 0x94000000 | imm26)
            cur = data[off : off + 4]
            if cur == bl_bytes or cur == nop4:
                if cur == nop4 and f_start == ms_off:
                    # 仅匹配紧接在参数准备指令后的调用位点
                    prev_w = struct.unpack_from("<I", data, off - 4)[0]
                    if (prev_w & 0xFF000000) not in (0xAA000000, 0x91000000, 0xF9000000, 0x52000000):
                        continue
                if cur == nop4 and f_start == ct_off and off < f_start + f_sz - 24:
                    continue
                res.append((off, bl_bytes))
        return res if len(res) == expected else None

    b_ct = find_arm64_bl(ct_off, ct_sz, 1)
    b_ms = find_arm64_bl(ms_off, ms_sz, 2)
    if not (b_ct and b_ms) or ui_zh:
        return None

    return [
        BinaryPatch("markdown_safe_wordwrap_margin", wrap_pos, wrap_orig, wrap_patched, v154[0].description),
        BinaryPatch("native_thought_slot_zh_fusion", sc_off + r_fusion, v154[1].original, v154[1].patched, v154[1].description),
        BinaryPatch("step_content_render_fused_snippet", sc_off + r_snip, snip_orig, snip_pat, v154[2].description),
        BinaryPatch("step_content_low_verbosity_keep_thought", sc_off + r_low, bytes.fromhex("080100b4"), bytes.fromhex("08000014"), v154[3].description),
        BinaryPatch("step_content_live_suppress_dup_body", sc_off + sup_hits[0][0], sup_hits[0][1], sup_hits[0][2], v154[4].description),
        BinaryPatch("step_content_done_suppress_dup_body", sc_off + sup_hits[1][0], sup_hits[1][1], sup_hits[1][2], v154[5].description),
        BinaryPatch("collapsed_thinking_keep_paragraphs", ct_off + r_para, v154[6].original, v154[6].patched, v154[6].description),
        BinaryPatch("collapsed_thinking_no_ellipsis_trunc", b_ct[0][0], b_ct[0][1], bytes.fromhex("1f2003d5"), v154[7].description),
        BinaryPatch("milestone_thinking_no_trunc_1", b_ms[0][0], b_ms[0][1], bytes.fromhex("1f2003d5"), v154[8].description),
        BinaryPatch("milestone_thinking_no_trunc_2", b_ms[1][0], b_ms[1][1], bytes.fromhex("1f2003d5"), v154[9].description),
    ]


def _matches_profile(data: bytes, patches: List[BinaryPatch]) -> bool:
    for p in patches:
        if len(data) < p.offset + len(p.original):
            return False
        seg = data[p.offset : p.offset + len(p.original)]
        if seg != p.original and seg != p.patched:
            return False
    return True


def detect_binary_profile(data: bytes, ui_zh: bool = False) -> Tuple[str, List[BinaryPatch]]:
    if data[:4] == MACHO_MAGIC_64_LE:
        cand = get_macos_arm64_v154_core_patches()
        if ui_zh:
            cand.extend(get_macos_arm64_v154_ui_patches())
        if _matches_profile(data, cand):
            return "macOS ARM64 Mach-O (agy v1.5.4)", cand
        auto_mac = _auto_locate_macos_arm64(data, ui_zh=ui_zh)
        if auto_mac is not None:
            return "macOS ARM64 Mach-O (gopclntab 自适应定位)", auto_mac
        return "macOS ARM64 Mach-O", cand

    if data[:4] == ELF_MAGIC:
        for label, core_fn, ui_fn in [
            ("Linux x86_64 ELF (agy v1.5.11)", get_linux_x86_64_v1511_core_patches, get_linux_x86_64_v1511_ui_patches),
            ("Linux x86_64 ELF (agy v1.5.9)", get_linux_x86_64_v159_core_patches, get_linux_x86_64_v159_ui_patches),
        ]:
            cand = core_fn()
            if ui_zh:
                cand.extend(ui_fn())
            if _matches_profile(data, cand):
                return label, cand

        auto_patches = _auto_locate_linux_x86_64(data, ui_zh=ui_zh)
        if auto_patches is not None:
            return "Linux x86_64 ELF (gopclntab 自适应定位)", auto_patches

        # 回退至最新静态表以便输出清晰的逐项偏移诊断信息
        fallback = get_linux_x86_64_v1511_core_patches()
        if ui_zh:
            fallback.extend(get_linux_x86_64_v1511_ui_patches())
        return "Linux x86_64 ELF", fallback

    if data[:2] == PE_MAGIC:
        raise RuntimeError(
            "检测到 Windows PE 可执行文件 (agy.exe)。请复制 README.md 中的 Windows AI 自动适配提示词，"
            "交由 AI 自动定位当前版本偏移并写入 patch_agy.py。"
        )
    raise RuntimeError(f"无法识别的可执行文件头魔数: {data[:4].hex()}")


# ============================================================================
# 3. 补丁应用、备份防降级与签名校验流程
# ============================================================================


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

    # 检测 agy 是否因官方升级发生了版本变更，避免旧备份反向降级新客户端
    if os.path.exists(backup_path) and os.path.abspath(source_path) != os.path.abspath(backup_path):
        src_ver = get_cli_version(source_path)
        bak_ver = get_cli_version(backup_path)
        if src_ver and bak_ver and src_ver != bak_ver:
            print(
                f"[升级同步] 检测到系统 agy 版本 ({src_ver}) 与现有备份 ({bak_ver}) 不一致，正在对齐当前版本备份..."
            )
            if not dry_run:
                shutil.copy2(source_path, backup_path)

    if not os.path.exists(backup_path) and not dry_run:
        print(f"[备份] 正在将原版二进制安全备份至: {backup_path}")
        shutil.copy2(source_path, backup_path)

    base_source = backup_path if os.path.exists(backup_path) else source_path
    with open(base_source, "rb") as f:
        data = bytearray(f.read())

    profile_name, patches = detect_binary_profile(bytes(data), ui_zh=ui_zh)
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
                f"  可能原因: 当前 agy 渲染结构发生较大变动，已安全中止写入。\n"
                f"  适配方法: 可直接使用 README.md 中的 AI 自动适配提示词更新新版本偏移。\n"
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
    parser = argparse.ArgumentParser(description="Antigravity CLI 原生思考槽位中文合流与渲染修复补丁引擎")
    parser.add_argument("--source", default=DEFAULT_SOURCE, help="原版 agy 路径")
    parser.add_argument("--backup", default=DEFAULT_BACKUP, help="隔离目录中的原版备份路径 (agy.orig)")
    parser.add_argument("--target", default=DEFAULT_TARGET, help="增强版输出路径 (agy-zh)")
    parser.add_argument("--ui-zh", action="store_true", help="同时汉化 Thought for / ctrl+o 等 UI 状态标签 (macOS & Linux)")
    parser.add_argument("--dry-run", action="store_true", help="仅校验偏移与字节特征，不写入文件")
    args = parser.parse_args()
    apply_patches(args.source, args.backup, args.target, args.ui_zh, args.dry_run)


if __name__ == "__main__":
    main()
