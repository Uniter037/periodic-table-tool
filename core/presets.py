# -*- coding: utf-8 -*-
"""预设管理：将绘图设置（模式、参数、颜色、数据等）保存为命名 JSON 预设。

预设文件存放在指定目录（默认项目根 presets/），每个预设一个 .json 文件。
预设名仅允许字母、数字、下划线、连字符与中文，防止路径穿越。
"""
from __future__ import annotations

import json
import os
import re

_NAME_RE = re.compile(r"^[\w\u4e00-\u9fff-]{1,40}$")


class PresetStore:
    """JSON 预设的保存 / 加载 / 列出 / 删除。"""

    def __init__(self, dir_path: str):
        self.dir_path = dir_path
        os.makedirs(self.dir_path, exist_ok=True)

    # ------------------------------------------------------------------
    def _path_for(self, name: str) -> str:
        if not _NAME_RE.match(name or ""):
            raise ValueError(
                "预设名仅允许字母、数字、下划线、连字符与中文（1~40 字符）")
        return os.path.join(self.dir_path, f"{name}.json")

    def save(self, name: str, payload: dict) -> str:
        """保存预设，返回文件路径。"""
        path = self._path_for(name)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        return path

    def load(self, name: str) -> dict:
        """加载预设。"""
        path = self._path_for(name)
        if not os.path.exists(path):
            raise FileNotFoundError(f"预设不存在: {name}")
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)

    def list(self) -> list:
        """列出全部预设名（按名称排序）。"""
        names = []
        for f in os.listdir(self.dir_path):
            if f.endswith(".json"):
                names.append(f[:-5])
        return sorted(names)

    def delete(self, name: str):
        """删除预设。"""
        path = self._path_for(name)
        if os.path.exists(path):
            os.remove(path)
