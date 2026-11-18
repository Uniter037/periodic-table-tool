"""Immutable geometry only; no measurements or rendering dependencies."""
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Cell:
    number: int
    symbol: str
    group: int
    period: int
    x: float
    y: float
    width: float = 1.0
    height: float = 1.0

    @property
    def bounds(self):
        return (self.x, self.y, self.width, self.height)


@dataclass(frozen=True)
class SeriesMarker:
    lines: tuple[str, ...]
    x: float
    y: float
    boxed: bool = False


@dataclass(frozen=True)
class PlotLayout:
    name: str
    cells: tuple[Cell, ...]
    markers: tuple[SeriesMarker, ...]
    hidden_elements: tuple[str, ...]
    bounds: tuple[float, float, float, float]


# Period rows are chemical identities, independent of any renderer or value DTO.
_ROWS = (
    'H He', 'Li Be B C N O F Ne', 'Na Mg Al Si P S Cl Ar',
    'K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge As Se Br Kr',
    'Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe',
    'Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn',
    'Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr Rf Db Sg Bh Hs Mt Ds Rg Cn Nh Fl Mc Lv Ts Og',
)


@lru_cache(maxsize=2)
def build_layout(layout: str) -> PlotLayout:
    """expanded has 118 cells; compact hides both complete fifteen-element series.

    Coordinates and cell bounds use a bottom-left origin in plot data units.
    ``hidden_elements`` is the authoritative list for application reporting.
    """
    if layout not in ('expanded', 'compact'):
        raise ValueError(f'Unknown plot layout: {layout!r}')
    height = 11.0 if layout == 'expanded' else 8.7
    cells, hidden = [], []
    number = 0
    for period, row in enumerate(_ROWS, 1):
        symbols = row.split()
        for index, symbol in enumerate(symbols):
            number += 1
            series = 57 <= number <= 71 or 89 <= number <= 103
            if series:
                if layout == 'compact':
                    hidden.append(symbol)
                    continue
                group = number - (57 if number <= 71 else 89) + 3
                display_period = 8 if number <= 71 else 9
            else:
                display_period = period
                if period == 1:
                    group = (1, 18)[index]
                elif period in (2, 3):
                    group = (1, 2, 13, 14, 15, 16, 17, 18)[index]
                else:
                    group = index + 1 - (14 if period >= 6 and index >= 17 else 0)
            x = 1.1 * (group - 1)
            y = height - 1.1 * display_period - (0.5 if display_period >= 8 else 0)
            cells.append(Cell(number, symbol, group, display_period, x, y))
    markers = []
    for period, lines in ((6, ('57–71', 'La–Lu', 'Lanthanide')),
                          (7, ('89–103', 'Ac–Lr', 'Actinide'))):
        y = height - 1.1 * period
        markers.append(SeriesMarker(lines if layout == 'compact' else (lines[1],),
                                    2.2, y, layout == 'compact'))
    return PlotLayout(layout, tuple(cells), tuple(markers), tuple(hidden), (0., 0., 20., height))
