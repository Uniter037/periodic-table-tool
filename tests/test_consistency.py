# -*- coding: utf-8 -*-
"""一致性测试（unittest）。

将 13 种绘图模式与原脚本输出逐像素对比。
运行: python -m unittest discover -s tests -v
"""
from __future__ import annotations

import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "tests"))

import verify


class TestConsistency(unittest.TestCase):
    """每种模式与原脚本输出逐像素一致性。"""

    def test_all_styles(self):
        results = verify.verify_all()
        for sid, status, msg in results:
            with self.subTest(style=sid):
                self.assertEqual(status, "PASS", f"{sid}: {msg}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
