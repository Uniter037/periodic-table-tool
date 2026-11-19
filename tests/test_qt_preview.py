"""Offscreen Qt packet-preview tests in clean processes at two display DPRs."""
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]

_SCRIPT = r'''
import math
import sys
from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QImage, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from ui.qt.preview import PreviewCanvas

app = QApplication([])
widget = PreviewCanvas()
widget.resize(600, 400)
widget.show()
app.processEvents()
assert math.isclose(widget.devicePixelRatioF(), float(sys.argv[2]), rel_tol=.01)
assert widget.source_image is None and widget.pixel_hits == {} and widget.zoom_label == '—'
source = QImage(400, 200, QImage.Format.Format_ARGB32)
source.fill(QColor('#ffffff'))
source.setPixelColor(120, 80, QColor('#ff0000'))
buffer = QBuffer()
assert buffer.open(QIODevice.OpenModeFlag.WriteOnly)
assert source.save(buffer, 'PNG')
png = bytes(buffer.data())
hits = {(100, 50, 200, 150): 'Fe', (10, 10, 60, 40): 'H'}
selected, moves, bars, zooms = [], [], [], []
widget.elementSelected.connect(selected.append)
widget.labelMoved.connect(lambda *args: moves.append(args))
widget.colorbarMoved.connect(lambda *args: bars.append(args))
widget.zoomChanged.connect(zooms.append)
widget.show_packet(png, hits)
app.processEvents()

# Public view mapping: fit fills the viewport, with centered letterboxing.
def point(x, y, actual=False, pan=(0, 0)):
    scale = 1 / widget.devicePixelRatioF() if actual else min(widget.width()/400, widget.height()/200)
    return QPoint(round((widget.width()-400*scale)/2 + x*scale + pan[0]),
                  round((widget.height()-200*scale)/2 + y*scale + pan[1]))

def drag(start, end, button=Qt.MouseButton.LeftButton):
    QTest.mousePress(widget, button, Qt.KeyboardModifier.NoModifier, start)
    QTest.mouseMove(widget, end)
    QTest.mouseRelease(widget, button, Qt.KeyboardModifier.NoModifier, end)
    app.processEvents()

try:
    scenario = sys.argv[1]
    if scenario == 'packet':
        assert isinstance(widget.source_image, QImage)
        assert widget.source_image.size() == source.size()
        assert widget.source_image.pixelColor(120, 80) == QColor('#ff0000')
        assert widget.source_image.devicePixelRatio() == 1
        hits.clear()
        assert len(widget.pixel_hits) == 2
        detached = widget.pixel_hits
        detached.clear()
        copy = widget.source_image
        copy.fill(QColor('black'))
        assert len(widget.pixel_hits) == 2
        assert widget.source_image.pixelColor(120, 80) == QColor('red')
        for bad_png, bad_hits in [(b'broken', {}), (png, {(0, 0, 0, 1): 'H'})]:
            try:
                widget.show_packet(bad_png, bad_hits)
            except ValueError:
                pass
            else:
                raise AssertionError('Invalid packet accepted')
            assert len(widget.pixel_hits) == 2
            assert widget.source_image.pixelColor(120, 80) == QColor('red')
        widget.set_selected('Fe')
        app.processEvents()
        screen = widget.grab().toImage()
        assert not screen.isNull()
        # Outline is rendered as an overlay, never burned into packet pixels.
        p = point(100, 100)
        dpr = screen.devicePixelRatio()
        assert screen.pixelColor(round(p.x()*dpr), round(p.y()*dpr)) == QColor('#2563eb')
        assert widget.source_image.pixelColor(100, 100) == QColor('white')
        widget.set_stale(True)
        assert widget.is_stale
        app.processEvents()
        banner = widget.grab().toImage()
        assert banner.pixelColor(round(8*dpr), round(8*dpr)) == QColor('#fff1d6')
        QTest.mouseClick(widget, Qt.MouseButton.LeftButton, pos=point(150, 100))
        assert not selected
        assert widget.source_image.pixelColor(120, 80) == QColor('red')
        widget.set_stale(False)
        assert not widget.is_stale

    elif scenario == 'numpy_hits':
        import numpy as np
        # Real rasterize output uses tuples of numpy.float64 bounding coordinates.
        for scalar in (np.float64, np.float32, np.int64):
            numpy_hits = {tuple(scalar(v) for v in box): symbol for box, symbol in hits.items()}
            widget.show_packet(png, numpy_hits)
            assert widget.pixel_hits == hits
            assert all(type(v) is float for box in widget.pixel_hits for v in box)
            selected.clear()
            QTest.mouseClick(widget, Qt.MouseButton.LeftButton, pos=point(150, 100))
            assert selected == ['Fe']
            drag(point(150, 100), point(175, 120))
            assert moves[-1][0] == 'Fe'
            assert math.isclose(moves[-1][1], .25, abs_tol=.005)
            assert math.isclose(moves[-1][2], -.2, abs_tol=.005)
        before = widget.pixel_hits
        for invalid in (np.float64('nan'), np.float64('inf'), np.float32('-inf'),
                        np.bool_(True), True, '100', 1 + 2j, 10**1000):
            try:
                widget.show_packet(png, {(invalid, 50, 200, 150): 'Fe'})
            except ValueError:
                pass
            else:
                raise AssertionError('Invalid scalar accepted: ' + repr(invalid))
            assert widget.pixel_hits == before
            assert widget.source_image.pixelColor(120, 80) == QColor('red')

    elif scenario == 'interaction':
        QTest.mouseClick(widget, Qt.MouseButton.LeftButton, pos=point(150, 100))
        assert selected == ['Fe'] and not moves
        drag(point(150, 100), point(175, 120))
        assert moves[-1][0] == 'Fe'
        assert math.isclose(moves[-1][1], .25, abs_tol=.005)
        assert math.isclose(moves[-1][2], -.2, abs_tol=.005)
        widget.set_edit_enabled(False)
        count = len(moves)
        drag(point(150, 100), point(175, 120))
        assert len(moves) == count
        widget.set_edit_enabled(True)
        # Invalidate in the middle of a drag: release must not emit an edit.
        QTest.mousePress(widget, Qt.MouseButton.LeftButton, pos=point(150, 100))
        widget.set_stale(True)
        QTest.mouseRelease(widget, Qt.MouseButton.LeftButton, pos=point(175, 120))
        assert len(moves) == count
        widget.set_stale(False)
        widget.set_colorbar_box((.8, .2, .1, .5))
        drag(point(340, 100), point(360, 120))
        assert len(bars) == 1
        assert math.isclose(bars[-1][0], .85, abs_tol=.005)
        assert math.isclose(bars[-1][1], .1, abs_tol=.005)
        # Clamping and bottom-left origin are independent of display scaling.
        drag(point(340, 100), point(800, -500))
        assert bars[-1] == (.9, .5)
        widget.set_colorbar_box(None)
        count = len(bars)
        drag(point(340, 100), point(360, 120))
        assert len(bars) == count
        widget.fit()
        selected.clear()
        drag(QPoint(300, 200), QPoint(330, 220), Qt.MouseButton.RightButton)
        assert not selected
        QTest.mouseClick(widget, Qt.MouseButton.LeftButton, pos=point(150, 100, pan=(30, 20)))
        assert selected == ['Fe']
        widget.fit()
        QTest.mousePress(widget, Qt.MouseButton.LeftButton, pos=point(150, 100))
        QTest.keyClick(widget, Qt.Key.Key_Escape)
        count = len(moves)
        QTest.mouseRelease(widget, Qt.MouseButton.LeftButton, pos=point(175, 120))
        assert len(moves) == count

    elif scenario == 'resize':
        assert widget.zoom_label == f'{1.5*widget.devicePixelRatioF():.0%}'
        widget.resize(800, 600)
        app.processEvents()
        assert widget.zoom_label == f'{2*widget.devicePixelRatioF():.0%}'
        QTest.mouseClick(widget, Qt.MouseButton.LeftButton, pos=point(150, 100))
        assert selected[-1] == 'Fe'
        widget.actual_size()
        assert widget.zoom_label == '100%'
        QTest.mouseClick(widget, Qt.MouseButton.LeftButton, pos=point(150, 100, actual=True))
        assert selected[-1] == 'Fe'
        drag(point(150, 100, actual=True), point(175, 120, actual=True))
        assert math.isclose(moves[-1][1], .25, abs_tol=.015)
        assert math.isclose(moves[-1][2], -.2, abs_tol=.015)
        widget.resize(500, 350)
        app.processEvents()
        assert widget.zoom_label == '100%'
        widget.zoom_in()
        assert widget.zoom_label == '115%'
        widget.zoom_out()
        assert widget.zoom_label == '100%'
        event = QWheelEvent(QPointF(200, 150), QPointF(200, 150), QPoint(), QPoint(0, 120),
                            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                            Qt.ScrollPhase.NoScrollPhase, False)
        QApplication.sendEvent(widget, event)
        assert widget.zoom_label == '115%'
        widget.fit()
        assert widget.zoom_label == f'{1.25*widget.devicePixelRatioF():.0%}'
        assert zooms and zooms[-1] == widget.zoom_label
    else:
        raise AssertionError(scenario)
    assert not {'tkinter', 'ui.preview', 'core.styles', 'core.options',
                'core.scientific', 'core.ptable', 'matplotlib'} & set(sys.modules)
finally:
    widget.close()
print('QT_PREVIEW_OK:' + scenario)
'''


@pytest.mark.parametrize('dpr', ['1', '2'])
@pytest.mark.parametrize('scenario', ['packet', 'interaction', 'resize', 'numpy_hits'])
def test_qt_preview_in_offscreen_process(tmp_path, scenario, dpr):
    script = tmp_path / 'qt_preview_scenario.py'
    script.write_text(_SCRIPT, encoding='utf-8')
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen', QT_SCALE_FACTOR=dpr,
               QT_AUTO_SCREEN_SCALE_FACTOR='0', PYTHONIOENCODING='utf-8')
    env.pop('QT_SCREEN_SCALE_FACTORS', None)
    env['PYTHONPATH'] = str(ROOT) + os.pathsep + env.get('PYTHONPATH', '')
    result = subprocess.run([sys.executable, str(script), scenario, dpr],
                            cwd=ROOT, env=env, capture_output=True, text=True,
                            encoding='utf-8', errors='replace', timeout=60)
    assert result.returncode == 0, f'{scenario} DPR={dpr}\n{result.stdout}\n{result.stderr}'
    assert 'QT_PREVIEW_OK:' + scenario in result.stdout
