"""Validated JSON configuration, independent of Tk, Matplotlib and script presets."""
from copy import deepcopy
from dataclasses import dataclass, field
import json
import math

from .data import _SYMBOLS


class PlotSpecError(ValueError):
    def __init__(self, path, message):
        self.path = path
        super().__init__(f'{path}: {message}')


_DEFAULTS = dict(
    kind='heatmap', layout='expanded', cmap='coolwarm', norm=['twoslope', -1, 0, 1],
    fmt='3f', rounding='half_up', font='Arial', figsize=[10, 5], dpi=100, title='',
    show_cbar=True, show_cbar_labels=True, preserve_cbar_space=False, check_label_overlap=True,
    bbox_tight=False, transparent=False, show_symbol=True, show_number=True, show_value=True,
    symbol_fs=9, number_fs=6, value_fs=6, value_dx=0, value_dy=0, label_wrap=0, unit='',
    edge=None, empty='#f0f0f0', bg='#f0f0f0', label_color='auto', label_fs=8,
    label_dy=.12, num_x=.2, num_ha='center', highlight_bg=None, highlight_fg=None,
    plain_bg=None, plain_fg=None, margins=None, cbar_box=None, cbar=None,
    cbar_orientation='vertical', cbar_location='auto', cbar_label='',
    cbar_fraction=.046, cbar_pad=.04, cbar_shrink=1, element_overrides={},
)


def _require(condition, path, message):
    if not condition:
        raise PlotSpecError(path, message)


def _number(value, path, low=None, high=None, positive=False):
    _require(type(value) in (int, float), path, 'must be a number, not bool')
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    _require(finite, path, 'must be finite')
    _require(not positive or value > 0, path, 'must be positive')
    _require(low is None or value >= low, path, f'must be >= {low}')
    _require(high is None or value <= high, path, f'must be <= {high}')


def _sequence(value, path, length=None):
    _require(isinstance(value, (list, tuple)), path, 'must be an array')
    _require(length is None or len(value) == length, path, f'must have {length} entries')


def _text(value, path, nonempty=False):
    _require(isinstance(value, str), path, 'must be text')
    _require(not nonempty or bool(value.strip()), path, 'must not be empty')


def _color(value, path):
    if isinstance(value, str):
        _text(value, path, True)
    else:
        _sequence(value, path)
        _require(len(value) in (3, 4), path, 'must be RGB or RGBA')
        for index, component in enumerate(value):
            _number(component, f'{path}[{index}]', 0, 1)


def _enum(value, path, choices):
    _require(isinstance(value, str) and value in choices, path, 'must be one of ' + ', '.join(choices))


def _validate(mapping):
    _require(isinstance(mapping, dict), 'plot', 'must be an object')
    extra = set(mapping) - set(_DEFAULTS)
    _require(not extra, 'plot', f'unknown fields: {sorted(map(str, extra))}')
    config = deepcopy(_DEFAULTS)
    config.update(deepcopy(mapping))
    enums = dict(kind=('heatmap', 'labels'), layout=('expanded', 'compact'),
        fmt=('raw', 'g', 'percent2', '2f', '3f', '4f', 'scientific'), rounding=('half_up', 'python'),
        num_ha=('left', 'center', 'right'), cbar_orientation=('vertical', 'horizontal'),
        cbar_location=('auto', 'left', 'right', 'top', 'bottom'))
    for key, choices in enums.items():
        _enum(config[key], key, choices)
    allowed_locations = ('auto', 'left', 'right') if config['cbar_orientation'] == 'vertical' else ('auto', 'top', 'bottom')
    _require(config['cbar_location'] in allowed_locations, 'cbar_location', 'conflicts with orientation')
    for key in ('show_cbar', 'show_cbar_labels', 'preserve_cbar_space', 'check_label_overlap',
                'bbox_tight', 'transparent', 'show_symbol', 'show_number', 'show_value'):
        _require(type(config[key]) is bool, key, 'must be boolean')
    for key in ('title', 'unit', 'cbar_label', 'font'):
        _text(config[key], key, key == 'font')
    for key in ('symbol_fs', 'number_fs', 'value_fs', 'label_fs'):
        _number(config[key], key, positive=True)
    for key in ('num_x', 'label_dy'):
        _number(config[key], key)
    for key, low, high in (('dpi', 36, 1200), ('value_dx', -2, 2), ('value_dy', -2, 2),
                           ('label_wrap', 0, 200), ('cbar_fraction', .005, .5),
                           ('cbar_pad', 0, .5), ('cbar_shrink', .05, 1)):
        _number(config[key], key, low, high)
    _require(config['label_wrap'] == int(config['label_wrap']), 'label_wrap', 'must be an integer')
    config['label_wrap'] = int(config['label_wrap'])
    _sequence(config['figsize'], 'figsize', 2)
    _number(config['figsize'][0], 'figsize[0]', 2, 40)
    _number(config['figsize'][1], 'figsize[1]', 1, 40)
    norm = config['norm']
    _sequence(norm, 'norm')
    _require(bool(norm), 'norm', 'must not be empty')
    _enum(norm[0], 'norm[0]', ('normalize', 'twoslope'))
    _sequence(norm, 'norm', 4 if norm[0] == 'twoslope' else 3)
    for i, value in enumerate(norm[1:], 1):
        _number(value, f'norm[{i}]')
    _require(all(a < b for a, b in zip(norm[1:], norm[2:])), 'norm', 'bounds must strictly increase')
    for key in ('empty', 'bg', 'label_color', 'highlight_bg', 'highlight_fg', 'plain_bg', 'plain_fg'):
        if config[key] is not None or key in ('empty', 'bg', 'label_color'):
            _color(config[key], key)
    if config['edge'] is not None:
        _sequence(config['edge'], 'edge', 2)
        _number(config['edge'][0], 'edge[0]', 0, 20)
        _color(config['edge'][1], 'edge[1]')
    cmap = config['cmap']
    if isinstance(cmap, str):
        _text(cmap, 'cmap', True)
        _require(':' not in cmap, 'cmap', 'module paths are not allowed')
    else:
        _sequence(cmap, 'cmap', 2)
        _require(cmap[0] == 'custom', 'cmap[0]', 'must be custom')
        colors = cmap[1]
        _sequence(colors, 'cmap[1]')
        _require(len(colors) >= 2, 'cmap[1]', 'needs at least two colors')
        nodes = isinstance(colors[0], (tuple, list)) and len(colors[0]) == 2
        positions = []
        for i, color in enumerate(colors):
            path = f'cmap[1][{i}]'
            if nodes:
                _sequence(color, path, 2)
                _number(color[0], path + '[0]', 0, 1)
                positions.append(color[0])
                _color(color[1], path + '[1]')
            else:
                _color(color, path)
        if nodes:
            _require(len(set(positions)) == len(positions), 'cmap', 'positions must be unique')
            _require(min(positions) == 0 and max(positions) == 1, 'cmap', 'positions must span 0 to 1')
            config['cmap'] = ['custom', sorted(colors, key=lambda row: row[0])]
    for key in ('margins', 'cbar_box'):
        box = config[key]
        if box is None:
            continue
        _sequence(box, key, 4)
        for i, value in enumerate(box):
            _number(value, f'{key}[{i}]', 0, 1)
        a, b, c, d = box
        valid = a < c and b < d if key == 'margins' else c > 0 and d > 0 and a + c <= 1 and b + d <= 1
        _require(valid, key, 'invalid Figure region')
    bar = config['cbar']
    if bar is not None:
        _require(isinstance(bar, dict), 'cbar', 'must be an object')
        _require(not set(bar) - {'ticks', 'labels', 'visible', 'fontsize'}, 'cbar', 'unknown fields')
        for key in ('ticks', 'labels'):
            _require(key in bar, f'cbar.{key}', 'required')
            _sequence(bar[key], f'cbar.{key}')
        bar.setdefault('visible', [True] * len(bar['ticks']))
        bar.setdefault('fontsize', 8)
        _sequence(bar['visible'], 'cbar.visible')
        _require(len(bar['ticks']) == len(bar['labels']) == len(bar['visible']), 'cbar', 'row lengths differ')
        for i, tick in enumerate(bar['ticks']):
            _number(tick, f'cbar.ticks[{i}]')
            _text(bar['labels'][i], f'cbar.labels[{i}]')
            _require(type(bar['visible'][i]) is bool, f'cbar.visible[{i}]', 'must be boolean')
        _require(len(set(bar['ticks'])) == len(bar['ticks']), 'cbar.ticks', 'duplicate ticks')
        _number(bar['fontsize'], 'cbar.fontsize', positive=True)
    overrides = config['element_overrides']
    _require(isinstance(overrides, dict), 'element_overrides', 'must be an object')
    for symbol, edit in overrides.items():
        path = f'element_overrides.{symbol}'
        _require(symbol in _SYMBOLS, path, 'unknown element')
        _require(isinstance(edit, dict), path, 'must be an object')
        _require(not set(edit) - {'show_value', 'show_color', 'include_in_range', 'value_dx', 'value_dy'}, path, 'unknown fields')
        for key, value in edit.items():
            if key in ('value_dx', 'value_dy'):
                _number(value, path + '.' + key)
            else:
                _require(type(value) is bool, path + '.' + key, 'must be boolean')
    return config


@dataclass(frozen=True, init=False)
class PlotSpec:
    _serialized: str = field(repr=False)

    def __init__(self, mapping=None):
        config = _validate({} if mapping is None else mapping)
        object.__setattr__(self, '_serialized', json.dumps(config, ensure_ascii=False, allow_nan=False, sort_keys=True))

    @classmethod
    def from_dict(cls, mapping):
        _require(isinstance(mapping, dict), 'plot', 'must be an object')
        return cls(mapping)

    def to_dict(self):
        return json.loads(self._serialized)
