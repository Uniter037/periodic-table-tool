# -*- coding: utf-8 -*-
"""pytest 共享配置：确保项目根目录可被所有测试导入；共享 GUI 实例。"""
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest


@pytest.fixture(scope="session")
def app():
    """整个测试会话共享一个 GUI 实例（连续创建多个 Tk 根窗口在 Windows 会失败）。"""
    import main  # 业务导入失败必须使测试失败，不能伪装成环境跳过。
    instance = main.App()
    instance.withdraw()
    yield instance
    try:
        instance.destroy()
    except Exception:
        pass
