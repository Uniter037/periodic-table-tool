# -*- coding: utf-8 -*-
"""数据输入解析与校验。

支持三种输入方式：
1. 逐行格式：每行一个元素，如
       Ag, 0.0101
       Au = 0.0111
       Sc: 3c1          （标注类模式允许字符串值）
2. Python 字典文本：{'Ag': 0.0101, 'Au': 0.0111}
3. JSON 文本：{"Ag": 0.0101}
"""
from __future__ import annotations

import json
import re

from .elements_data import ALL_SYMBOLS

_SYMBOLS = set(ALL_SYMBOLS)


def known_symbols() -> set:
    """全部 118 个元素符号集合。"""
    return set(_SYMBOLS)


def parse_data(text: str) -> dict:
    """解析用户输入文本，返回 {元素符号: 值} 字典。

    值保留原始文本形态：能被 float() 解析则转 float，否则保留字符串
    （标注类模式使用字符串值，如 '3c1'）。
    """
    text = (text or "").strip()
    if not text:
        return {}

    # 1) 字典 / JSON 文本
    if text.startswith("{") and text.endswith("}"):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            # 尝试 Python 字面量（单引号、裸 True 等）
            try:
                parsed = _safe_eval_dict(text)
            except Exception:
                raise ValueError("无法解析字典格式的数据，请检查格式")
        result = {}
        for key, val in parsed.items():
            result[str(key).strip()] = _coerce(val)
        return result

    # 2) 逐行格式：符号 分隔符 值
    result = {}
    line_pattern = re.compile(r"^\s*([A-Za-z]{1,2})\s*[=:，,\t\s]\s*(.+?)\s*$")
    for lineno, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = line_pattern.match(line)
        if not m:
            raise ValueError(f"第 {lineno} 行无法解析: {line!r}")
        sym, val = m.group(1), m.group(2)
        result[sym] = _coerce(val)
    return result


def _coerce(val):
    """尽量转 float，失败则保留字符串。"""
    if isinstance(val, (int, float)):
        return val
    s = str(val).strip()
    try:
        return float(s)
    except ValueError:
        return s


def _safe_eval_dict(text: str) -> dict:
    """安全解析 Python 字典字面量（只允许基本类型）。"""
    import ast
    node = ast.literal_eval(text)
    if not isinstance(node, dict):
        raise ValueError("需要字典")
    return node


def validate_data(data: dict) -> tuple:
    """校验数据：返回 (合法字典, 未知符号列表, 非法值列表)。

    字符串值会尝试转为 float（GUI 表格中数值以文本形式存在）；
    无法转换的字符串原样保留（供标注类模式使用）。
    """
    unknown, bad = [], []
    valid = {}
    for sym, val in data.items():
        if sym not in _SYMBOLS:
            unknown.append(sym)
            continue
        if isinstance(val, bool):
            bad.append((sym, val))
            continue
        if isinstance(val, (int, float)):
            valid[sym] = val
        elif isinstance(val, str):
            try:
                valid[sym] = float(val)
            except ValueError:
                valid[sym] = val    # 标注类模式：保留字符串文本
        else:
            bad.append((sym, val))
    return valid, unknown, bad


def demo_data(style_id: str) -> dict:
    """返回指定样式的示例数据（取自原脚本），便于快速体验。"""
    if style_id == "reconstruct_percent":
        return {'Ag': 0.0101, 'Au': 0.0111, 'Pd': 0.0112, 'Pt': 0.0119, 'Cd': 0.0113, 'Co': 0.0104, 'Cr': 0.0121, 'Cu': 0.0110, 'Fe': 0.0115, 'Ir': 0.0135, 'Mn': 0.0118, 'Mo': 0.0095, 'Os': 0.0120, 'Re': 0.0123, 'Rh': 0.0115, 'Ru': 0.0109, 'Tc': 0.0110, 'Ti': 0.0109, 'W': 0.0114, 'Zn': 0.0103, 'Al': 0.0114, 'Mg': 0.0113, 'Zr': 0.0112, 'Ga': 0.0092, 'Ge': 0.0059, 'Nb': 0.0128, 'Ni': 0.0089, 'Sc': 0.0110, 'Ta': 0.0142, 'V': 0.0119, 'Y': 0.0107}
    if style_id == "reconstruct_2f_a":
        return {'Ag': -26.56, 'Au': -29.38, 'Pd': -32.58, 'Pt': -31.60, 'Cd': -25.40, 'Co': -34.12, 'Cr': -21.71, 'Cu': -31.25, 'Fe': -30.94, 'Ir': -29.01, 'Mn': -26.04, 'Mo': -14.37, 'Os': -21.53, 'Re': -15.40, 'Rh': -29.87, 'Ru': -24.77, 'Tc': -19.95, 'Ti': -20.62, 'W': -12.11, 'Zn': -24.71, 'Al': -31.81, 'Mg': -27.31, 'Zr': -29.95, 'Ga': -29.39, 'Ge': -26.39, 'Nb': -30.44, 'Ni': -24.56, 'Sc': -31.94, 'Ta': -35.51, 'V': -35.11, 'Y': -23.82}
    if style_id == "reconstruct_2f_b":
        return {'Sc': -7.06, 'Y': -4.71, 'Zr': -4.88, 'Hf': -8.52, 'V': -2.87, 'Nb': -4.72, 'Ta': -3.81, 'Cr': -11.49, 'Mo': -9.70, 'W': -8.64, 'Mn': -16.26, 'Tc': -16.56, 'Re': -10.48, 'Fe': -17.93, 'Ru': -16.73, 'Os': -16.20, 'Co': -19.06, 'Rh': -17.28, 'Ir': -17.73, 'Pd': -18.80, 'Pt': -20.30, 'Cu': -20.81, 'Ag': -20.31, 'Au': -18.92, 'Zn': -19.65, 'Cd': -22.21, 'Mg': -3.76, 'Al': -11.92, 'Ga': -6.39, 'Ge': -10.06}
    if style_id in ("labels_light", "labels_highlight"):
        return {'Sc': '3c1', 'Y': '3c2', 'Ti': '1b', 'Zr': '3c1', 'Hf': '3c1', 'V': '1b', 'Nb': '3c1', 'Ta': '3c2', 'Cr': '3c2', 'Mo': '1b', 'W': '1c', 'Mn': '1c', 'Tc': '1c', 'Re': '1c', 'Fe': '1a', 'Ru': '1b', 'Os': '1b', 'Co': '1a', 'Rh': '1c', 'Ir': '1a', 'Ni': '1b', 'Pd': '3c2', 'Pt': '3c1', 'Cu': '3c2', 'Ag': '3c1', 'Au': '3c2', 'Zn': '3c2', 'Cd': '3c1', 'Mg': '3c1', 'Al': '1b', 'Ga': '1b', 'Ge': '1c'}
    if style_id == "classic_ylorrd_orig" or style_id == "classic_ylorrd" or style_id == "classic_blues":
        return {'O': 9, 'Te': 9, 'F': 9, 'S': 9, 'Na': 9, 'K': 9, 'N': 8, 'Li': 8, 'I': 8, 'Rb': 8, 'Si': 7, 'Cd': 7, 'Cl': 7, 'Zn': 7, 'H': 7, 'Bi': 7, 'Br': 7, 'P': 6, 'Sn': 6, 'Ca': 6, 'Au': 6, 'Al': 5, 'As': 5, 'Ga': 5, 'C': 5, 'Ge': 5, 'Sr': 5, 'Se': 5, 'Be': 5, 'B': 5, 'Cs': 5, 'Mg': 5, 'Ag': 5, 'Pb': 4, 'In': 4, 'Ti': 4, 'Cu': 4, 'Zr': 4, 'Sb': 4, 'Tl': 4, 'Sc': 4, 'Y': 4, 'Hg': 4, 'Ba': 4, 'La': 4, 'Hf': 4, 'Og': 1}
    if style_id == "classic_ylgn":
        return {'Sc': 0.02631, 'Y': 0.01993, 'Ti': 0.00854, 'Zr': 0.02513, 'Hf': 0.03409, 'V': 0.04348, 'Nb': 0.04132, 'Ta': 0.03714, 'Cr': 0.03544, 'Mo': 0.0061, 'W': 0.00981, 'Mn': 0.04773, 'Tc': 0.01885, 'Re': 0.00753, 'Fe': 0.01284, 'Ru': 0.03721, 'Os': 0.01031, 'Co': 0.03128, 'Rh': 0.01512, 'Ir': 0.01961, 'Ni': 0.02203, 'Pd': 0.03444, 'Pt': 0.0386, 'Cu': 0.03278, 'Ag': 0.03364, 'Au': 0.03685, 'Zn': 0.03727, 'Cd': 0.03297, 'Hg': 0.03558, 'Al': 0.01879, 'Mg': 0.000197}
    if style_id in ("classic_coolwarm", "classic_coolwarm3"):
        return {'Sc': 0.74, 'Y': 0.75, 'Ti': 0.74, 'Zr': 0.75, 'Hf': 0.74, 'V': 0.73, 'Nb': 0.73, 'Ta': 0.74, 'Cr': 0.74, 'Mo': 0.73, 'W': 0.73, 'Mn': 0.73, 'Tc': 0.73, 'Re': 0.73, 'Fe': 0.73, 'Ru': 0.74, 'Os': 0.74, 'Co': 0.73, 'Rh': 0.74, 'Ir': 0.73, 'Ni': 0.73, 'Pd': 0.73, 'Pt': 0.74, 'Cu': 0.74, 'Ag': 0.73, 'Au': 0.74, 'Zn': 0.74, 'Cd': 0.73, 'Hg': 0.74, 'Al': 0.74, 'Mg': 0.74}
    if style_id == "classic_bwr3":
        return {'Sc': 0.02631, 'Y': 0.01993, 'Ti': 0.00854, 'Zr': 0.02513, 'Hf': 0.03409, 'V': 0.04348, 'Nb': 0.04132, 'Ta': 0.03714, 'Cr': 0.03544, 'Mo': 0.0061, 'W': 0.00981, 'Mn': 0.04773, 'Tc': 0.01885, 'Re': 0.00753, 'Fe': 0.01284, 'Ru': 0.03721, 'Os': 0.01031, 'Co': 0.03128, 'Rh': 0.01512, 'Ir': 0.01961, 'Ni': 0.02203, 'Pd': 0.03444, 'Pt': 0.0386, 'Cu': 0.03278, 'Ag': 0.03364, 'Au': 0.03685, 'Zn': 0.03727, 'Cd': 0.03297, 'Hg': 0.03558, 'Al': 0.01879, 'Mg': 0.000197}
    return {}
