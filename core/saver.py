# -*- coding: utf-8 -*-
"""输出自动改名保存。

每次生成自动使用新文件名，绝不覆盖已有文件：
    {基础名}_{YYYYMMDD_HHMMSS}{_序号}.{扩展名}
例如：periodic_table_20260804_153012.svg、
      periodic_table_20260804_153012_2.svg（同一秒内再生成时追加序号）
"""
from __future__ import annotations

import datetime
import os


def auto_name(out_dir: str, base: str, ext: str) -> str:
    """生成一个不冲突的输出文件路径（自动改名），并原子创建占位文件。

    使用 os.open(O_CREAT|O_EXCL) 原子创建占位文件，确保"绝不覆盖"语义
    （调用方随后保存时覆盖此占位文件）；冲突时自动尝试下一个序号。
    O_EXCL 同时避免检查与创建之间的 TOCTOU 竞态与符号链接跟随。
    """
    os.makedirs(out_dir, exist_ok=True)
    ext = ext.lstrip(".").lower()
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    counter = 1
    while True:
        suffix = "" if counter == 1 else f"_{counter}"
        candidate = os.path.join(out_dir, f"{base}_{stamp}{suffix}.{ext}")
        try:
            fd = os.open(candidate,
                         os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
            return candidate
        except FileExistsError:
            counter += 1


def save_figure(fig, out_dir: str, base: str, fmt: str = "svg", **kwargs) -> str:
    """保存 figure 到文件，自动改名，返回最终路径。

    保存失败时清理 auto_name 创建的占位文件，避免残留空文件占用名字。
    """
    path = auto_name(out_dir, base, fmt)
    try:
        fig.savefig(path, **kwargs)
    except Exception:
        try:
            os.remove(path)
        except OSError:
            pass
        raise
    return path
