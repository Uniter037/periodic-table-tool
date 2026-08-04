# -*- coding: utf-8 -*-
"""检查项目运行依赖。"""
import importlib

deps = [
    ("matplotlib", "绘图库"),
    ("mendeleev", "元素周期表数据（原脚本依赖）"),
    ("numpy", "数值计算"),
    ("tkinter", "GUI 界面（Python 自带）"),
]

ok = True
for name, desc in deps:
    try:
        mod = importlib.import_module(name)
        ver = getattr(mod, "__version__", "builtin")
        print(f"[OK] {name} {ver} - {desc}")
    except Exception as exc:
        ok = False
        print(f"[MISSING] {name} - {desc} ({exc})")

print("ALL_OK" if ok else "SOME_MISSING")
