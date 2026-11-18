"""Numeric formatting and annotated text artists, without legacy policies."""
from decimal import Decimal, ROUND_HALF_UP, localcontext
import textwrap


def format_value(value, fmt, rounding):
    if fmt == 'raw':
        return str(value)
    if fmt == 'g':
        return format(value, 'g')
    if fmt == 'scientific':
        if rounding == 'python':
            return format(value, '.3e')
        number = Decimal(str(value))
        exponent = number.adjusted() if number else 0
        with localcontext() as context:
            context.prec = max(32, len(number.as_tuple().digits) + 8)
            mantissa = number.scaleb(-exponent).quantize(Decimal('.001'), rounding=ROUND_HALF_UP)
            if abs(mantissa) >= 10:
                mantissa = mantissa / 10
                exponent += 1
            return f'{mantissa:.3f}e{exponent:+03d}'
    digits = 2 if fmt == 'percent2' else int(fmt[0])
    if rounding == 'python':
        result = format(value * 100 if fmt == 'percent2' else value, f'.{digits}f')
    else:
        number = Decimal(str(value))
        with localcontext() as context:
            context.prec = max(32, len(number.as_tuple().digits) + abs(number.adjusted()) + digits + 8)
            if fmt == 'percent2':
                number *= 100
            result = str(number.quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP))
    return result + ('%' if fmt == 'percent2' else '')


def measurement_text(value, config):
    text = (format_value(value, config['fmt'], config['rounding']) + config['unit']
            if config['kind'] == 'heatmap' else str(value))
    width = config['label_wrap']
    return '\n'.join(textwrap.fill(line, width) for line in text.split('\n')) if width else text


def tag(artist, symbol, role, bounds):
    artist._ptable_element = symbol
    artist._ptable_role = role
    artist._ptable_cell = bounds
    return artist


def draw_text(ax, config, symbol, role, bounds, x, y, text, fontsize, color='black', **kwargs):
    artist = ax.text(x, y, text, fontsize=fontsize, color=color, fontfamily=config['font'],
                     va='center', **kwargs)
    return tag(artist, symbol, role, bounds)
