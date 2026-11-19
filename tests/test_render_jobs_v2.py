"""Real spawn-worker integration for the next desktop adapter."""
from io import BytesIO
from pathlib import Path
import time

from PIL import Image
import pytest

from core.jobs import RenderJob


def run(job, task):
    job.start(task)
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        event = job.poll()
        if event and event[0] in ('done', 'error'):
            assert event[0] == 'done', event
            return event[1]
        time.sleep(.01)
    pytest.fail('spawn worker timed out')


@pytest.mark.parametrize('tight', [False, True])
def test_native_preview_matches_export_and_maps_all_elements(tight):
    task = {'engine': 'v2', 'mode': 'export', 'format': 'png', 'data': {'H': 'sample'},
            'plot': {'kind': 'labels', 'dpi': 72, 'figsize': [5, 3], 'bbox_tight': tight,
                     'show_cbar': False, 'highlight_bg': '#e63f37', 'show_value': False,
                     'show_symbol': False, 'show_number': False}}
    job = RenderJob()
    try:
        export = run(job, task)
        raw = Path(export['files'][0][0]).read_bytes()
        preview = run(job, {**task, 'mode': 'preview'})
        assert len(preview['hits']) == 118
        with Image.open(BytesIO(raw)) as saved, Image.open(BytesIO(preview['png'])) as shown:
            assert saved.size == shown.size
            assert saved.convert('RGBA').tobytes() == shown.convert('RGBA').tobytes()
            box = next(box for box, symbol in preview['hits'].items() if symbol == 'H')
            left, top, right, bottom = box
            assert shown.getpixel((int((left + right) / 2), int((top + bottom) / 2)))[:3] == (230, 63, 55)
    finally:
        job.cancel()


def test_high_dpi_preview_budget_does_not_change_export_geometry():
    task = {'engine': 'v2', 'mode': 'preview', 'data': {'Ni': '.82'},
            'plot': {'dpi': 72, 'figsize': [8, 4], 'bbox_tight': False},
            'preview_max_pixels': 1600}
    job = RenderJob()
    try:
        result = run(job, task)
        with Image.open(BytesIO(result['png'])) as shown:
            assert shown.size == (1600, 800)
        result = run(job, {**task, 'mode': 'export', 'format': 'png'})
        with Image.open(result['files'][0][0]) as saved:
            assert saved.size == (576, 288)
    finally:
        job.cancel()
