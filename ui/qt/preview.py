"""Packet-only Qt preview; source pixels and widget coordinates stay separate."""
from __future__ import annotations

import math
from numbers import Real

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import QWidget


class PreviewCanvas(QWidget):
    elementSelected = Signal(str)
    labelMoved = Signal(str, float, float)
    colorbarMoved = Signal(float, float)
    zoomChanged = Signal(str)
    viewportChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._image = None
        self._hits = {}
        self._stale = False
        self._selected = ''
        self._editable = True
        self._bar = None
        self._drag = self._ghost = self._pan_origin = None
        self._pan = QPointF()
        self._zoom = 1.0
        self._actual = False
        self._last_label = '—'
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(1, 1)
        self.setMouseTracking(True)

    @property
    def is_stale(self):
        return self._stale

    @property
    def source_image(self):
        return self._image.copy() if self._image is not None else None

    @property
    def pixel_hits(self):
        return dict(self._hits)

    @property
    def zoom_label(self):
        if self._image is None:
            return '—'
        # A source pixel at 100% occupies one physical display pixel.
        return f'{self._scale() * self.devicePixelRatioF():.0%}'

    def _scale(self):
        if self._image is None:
            return 1.0
        base = (1.0 / self.devicePixelRatioF() if self._actual else
                min(self.width() / self._image.width(), self.height() / self._image.height()))
        return max(base * self._zoom, 1e-12)

    def _image_rect(self):
        if self._image is None:
            return QRectF()
        scale = self._scale()
        width, height = self._image.width() * scale, self._image.height() * scale
        return QRectF((self.width() - width) / 2 + self._pan.x(),
                      (self.height() - height) / 2 + self._pan.y(), width, height)

    def _source_point(self, position):
        rect = self._image_rect()
        return (position - rect.topLeft()) / self._scale()

    def _screen_rect(self, box):
        x0, y0, x1, y1 = box
        scale = self._scale()
        origin = self._image_rect().topLeft()
        return QRectF(origin.x() + x0 * scale, origin.y() + y0 * scale,
                      (x1 - x0) * scale, (y1 - y0) * scale)

    def _bar_pixels(self, box):
        x, y, width, height = box
        sw, sh = self._image.width(), self._image.height()
        return x * sw, (1 - y - height) * sh, (x + width) * sw, (1 - y) * sh

    def _changed(self):
        label = self.zoom_label
        if label != self._last_label:
            self._last_label = label
            self.zoomChanged.emit(label)
        self.update()

    def _cancel_drag(self):
        self._drag = self._ghost = self._pan_origin = None
        self.update()

    def show_packet(self, png: bytes, pixel_hits: dict):
        image = QImage.fromData(png, 'PNG')
        if image.isNull():
            raise ValueError('Invalid preview PNG')
        hits = {}
        for box, symbol in dict(pixel_hits).items():
            if (not isinstance(box, tuple) or len(box) != 4 or
                    not isinstance(symbol, str) or
                    any(isinstance(v, bool) or not isinstance(v, Real) for v in box)):
                raise ValueError('Invalid preview hit rectangle')
            try:
                # RenderJob rasterization supplies NumPy real scalars. Normalize
                # them here so subsequent Qt arithmetic uses plain Python floats.
                coordinates = tuple(float(v) for v in box)
            except (ValueError, TypeError, OverflowError) as exc:
                raise ValueError('Invalid preview hit rectangle') from exc
            if (not all(math.isfinite(v) for v in coordinates) or
                    coordinates[2] <= coordinates[0] or coordinates[3] <= coordinates[1]):
                raise ValueError('Invalid preview hit rectangle')
            hits[coordinates] = symbol
        # PNG metadata must not silently change the source-pixel coordinate system.
        image.setDevicePixelRatio(1.0)
        self._cancel_drag()
        self._image, self._hits = image, hits
        self._changed()

    def set_stale(self, stale):
        self._stale = bool(stale)
        if self._stale:
            self._cancel_drag()
        self.update()

    def set_selected(self, symbol):
        self._selected = symbol
        self.update()

    def set_edit_enabled(self, enabled):
        self._editable = bool(enabled)
        self._cancel_drag()

    def set_colorbar_box(self, box):
        if box is not None:
            box = tuple(float(v) for v in box)
            if (len(box) != 4 or not all(math.isfinite(v) for v in box) or
                    min(box) < 0 or box[2] <= 0 or box[3] <= 0 or
                    box[0] + box[2] > 1 or box[1] + box[3] > 1):
                raise ValueError('Colorbar must fit within normalized figure coordinates')
        self._bar = box
        self._cancel_drag()

    def fit(self):
        self._cancel_drag()
        self._actual, self._zoom, self._pan = False, 1.0, QPointF()
        self._changed()

    def actual_size(self):
        self._cancel_drag()
        self._actual, self._zoom, self._pan = True, 1.0, QPointF()
        self._changed()

    def _zoom_by(self, factor):
        self._cancel_drag()
        self._zoom = max(.25, min(8.0, self._zoom * factor))
        self._changed()

    def zoom_in(self):
        self._zoom_by(1.15)

    def zoom_out(self):
        self._zoom_by(1 / 1.15)

    def resizeEvent(self, event):
        self._cancel_drag()
        super().resizeEvent(event)
        self._changed()
        self.viewportChanged.emit()

    def event(self, event):
        result = super().event(event)
        if event.type() == QEvent.Type.DevicePixelRatioChange and hasattr(self, '_image'):
            self._cancel_drag()
            self._changed()
            self.viewportChanged.emit()
        return result

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor('#e5e7eb'))
        if self._image is not None:
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.fillRect(self._image_rect(), Qt.GlobalColor.white)
            painter.drawImage(self._image_rect(), self._image,
                              QRectF(0, 0, self._image.width(), self._image.height()))
            painter.setPen(QPen(QColor('#2563eb'), 2))
            for box, symbol in self._hits.items():
                if symbol == self._selected:
                    painter.drawRect(self._screen_rect(box))
            if self._bar is not None and self._editable and not self._stale:
                painter.drawRect(self._screen_rect(self._bar_pixels(self._bar)))
            if self._ghost is not None:
                painter.setPen(QPen(QColor('#2563eb'), 2, Qt.PenStyle.DashLine))
                painter.drawRect(self._screen_rect(self._ghost))
        if self._stale:
            banner = QRectF(6, 6, max(0, self.width() - 12), 28)
            painter.fillRect(banner, QColor('#fff1d6'))
            painter.setPen(QColor('#8a3b12'))
            painter.drawText(banner.adjusted(6, 0, -6, 0),
                             Qt.AlignmentFlag.AlignVCenter, '旧预览 · 当前设置或数据已更改')
        painter.end()

    def mousePressEvent(self, event):
        self._cancel_drag()
        self.setFocus()
        if event.button() == Qt.MouseButton.RightButton:
            self._pan_origin = (event.position(), QPointF(self._pan))
            event.accept()
            return
        if event.button() != Qt.MouseButton.LeftButton or self._image is None or self._stale:
            return
        point = self._source_point(event.position())
        if not (0 <= point.x() < self._image.width() and 0 <= point.y() < self._image.height()):
            return
        if self._editable and self._bar is not None:
            x0, y0, x1, y1 = self._bar_pixels(self._bar)
            if x0 <= point.x() <= x1 and y0 <= point.y() <= y1:
                self._drag = ('bar', event.position(), point, self._bar)
                return
        for box, symbol in self._hits.items():
            x0, y0, x1, y1 = box
            if x0 <= point.x() <= x1 and y0 <= point.y() <= y1:
                if self._editable:
                    self.set_selected(symbol)
                    self._drag = ('element', event.position(), point, (symbol, box))
                self.elementSelected.emit(symbol)
                break

    def _moved_bar(self, box, delta):
        x, y, width, height = box
        return (max(0., min(1 - width, x + delta.x() / self._image.width())),
                max(0., min(1 - height, y - delta.y() / self._image.height())), width, height)

    def mouseMoveEvent(self, event):
        if self._pan_origin is not None:
            origin, pan = self._pan_origin
            self._pan = pan + event.position() - origin
            self.update()
        elif self._drag is not None:
            kind, start, origin, payload = self._drag
            delta = self._source_point(event.position()) - origin
            travel = event.position() - start
            if travel.x() ** 2 + travel.y() ** 2 > 16:
                if kind == 'bar':
                    self._ghost = self._bar_pixels(self._moved_bar(payload, delta))
                else:
                    _, (x0, y0, x1, y1) = payload
                    self._ghost = (x0 + delta.x(), y0 + delta.y(), x1 + delta.x(), y1 + delta.y())
                self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self._pan_origin = None
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        drag = self._drag
        self._cancel_drag()
        if drag is None or not self._editable or self._stale:
            return
        kind, start, origin, payload = drag
        travel = event.position() - start
        if travel.x() ** 2 + travel.y() ** 2 <= 16:
            return
        delta = self._source_point(event.position()) - origin
        if kind == 'bar':
            x, y, _, _ = self._moved_bar(payload, delta)
            self.colorbarMoved.emit(x, y)
        else:
            symbol, (x0, y0, x1, y1) = payload
            self.labelMoved.emit(symbol, delta.x() / (x1 - x0), -delta.y() / (y1 - y0))

    def wheelEvent(self, event):
        delta = event.angleDelta().y() or event.pixelDelta().y()
        if delta:
            self._zoom_by(1.15 if delta > 0 else 1 / 1.15)
            event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._cancel_drag()
        else:
            super().keyPressEvent(event)
