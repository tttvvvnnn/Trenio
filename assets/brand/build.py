"""Собирает SVG-файлы логотипа Trenio.

Знак: секундомер, кнопка которого складывается в букву T, а на циферблате
закрашен забронированный отрезок времени. Слово trenio набрано Rubik ExtraBold
(800) и переведено в кривые, вместо буквы o стоит тот же секундомер.

Запуск (нужны fonttools и вариативный Rubik[wght].ttf из Google Fonts):
    python3 -m pip install fonttools
    python3 assets/brand/build.py path/to/Rubik[wght].ttf
PNG-версии экспортируются из этих SVG, см. assets/brand/README.md.
"""

import math
import sys
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

CORAL = '#FF5A36'
GRAPHITE = '#15171C'
WHITE = '#FFFFFF'
CONCRETE = '#EDEDEA'

OUT = Path(__file__).parent
PUBLIC = OUT.parent.parent / 'frontend' / 'public'


def f(v: float) -> str:
    return f'{v:.2f}'.rstrip('0').rstrip('.')


def rect(x, y, w, h, r=0.0) -> str:
    """Прямоугольник со скруглёнными углами как путь."""
    if not r:
        return f'M{f(x)} {f(y)}H{f(x + w)}V{f(y + h)}H{f(x)}Z'
    return (
        f'M{f(x + r)} {f(y)}H{f(x + w - r)}A{f(r)} {f(r)} 0 0 1 {f(x + w)} {f(y + r)}'
        f'V{f(y + h - r)}A{f(r)} {f(r)} 0 0 1 {f(x + w - r)} {f(y + h)}'
        f'H{f(x + r)}A{f(r)} {f(r)} 0 0 1 {f(x)} {f(y + h - r)}'
        f'V{f(y + r)}A{f(r)} {f(r)} 0 0 1 {f(x + r)} {f(y)}Z'
    )


def circle(cx, cy, r) -> str:
    return (
        f'M{f(cx - r)} {f(cy)}A{f(r)} {f(r)} 0 1 1 {f(cx + r)} {f(cy)}'
        f'A{f(r)} {f(r)} 0 1 1 {f(cx - r)} {f(cy)}Z'
    )


def wedge(cx, cy, r, deg=120) -> str:
    """Сектор циферблата от 12 часов по часовой стрелке."""
    a = math.radians(deg)
    return (
        f'M{f(cx)} {f(cy)}L{f(cx)} {f(cy - r)}'
        f'A{f(r)} {f(r)} 0 0 1 {f(cx + r * math.sin(a))} {f(cy - r * math.cos(a))}Z'
    )


def mark_paths():
    """Знак в квадрате 100×100: (корпус, сектор, ось стрелки)."""
    body = ' '.join([
        rect(29, 4, 42, 12, 3),  # перекладина T, она же кнопка
        rect(43, 12, 14, 19),  # ножка T, заходит в корпус
        # боковая кнопка, повёрнутая на 45°
        'M75.29 23.64L82.36 30.71L76.71 36.36L69.64 29.29Z',
        circle(50, 62, 33),
    ])
    return body, wedge(50, 62, 24), circle(50, 62, 4)


def watch_glyph(x, r):
    """Секундомер вместо o в слове; базовая линия y=0, возвращает (корпус, сектор, ширина)."""
    cx, cy = x + r, -r
    body = ' '.join([
        circle(cx, cy, r),
        rect(cx - r * 0.34, cy - r * 1.5, r * 0.68, r * 0.2, r * 0.05),
        rect(cx - r * 0.12, cy - r * 1.32, r * 0.24, r * 0.36),
    ])
    return body, wedge(cx, cy, r * 0.72), 2 * r


def word_paths(font_path: str):
    font = instantiateVariableFont(TTFont(font_path), {'wght': 800})
    glyphs, cmap = font.getGlyphSet(), font.getBestCmap()
    em = font['head'].unitsPerEm
    track = -0.02 * em
    x, parts, top = 0.0, [], 0.0
    for ch in 'treni':
        g = glyphs[cmap[ord(ch)]]
        pen = SVGPathPen(glyphs)
        g.draw(TransformPen(pen, (1, 0, 0, -1, x, 0)))
        parts.append(pen.getCommands())
        bounds = BoundsPen(glyphs)
        g.draw(bounds)
        top = max(top, bounds.bounds[3])
        x += g.width + track
    x += 0.06 * em  # чуть больше воздуха перед секундомером
    r = font['OS/2'].sxHeight * 1.06 / 2
    body, sector, width = watch_glyph(x, r)
    return ' '.join(parts) + ' ' + body, sector, x + width, max(top, r * 2.5)


def mono(color: str, body: str, sector: str, extra: str = '') -> str:
    """Одноцветная версия: сектор вырезан из корпуса маской, фон просвечивает."""
    return (
        '<mask id="cut"><rect x="-9999" y="-9999" width="99999" height="99999" fill="#fff"/>'
        f'<path fill="#000" d="{sector}"/></mask>'
        f'<path fill="{color}" mask="url(#cut)" d="{body}"/>'
        + (f'<path fill="{color}" d="{extra}"/>' if extra else '')
    )


def svg(view_box: str, body: str, extra: str = '') -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view_box}"{extra}>'
        f'{body}</svg>\n'
    )


def write(path: Path, content: str) -> None:
    path.write_text(content)
    print(path.relative_to(OUT.parent.parent))


def main(font_path: str) -> None:
    body, sector, dot = mark_paths()
    mark_vb = '14 2 72 96'

    # Знак: цветной, инверсия для тёмного фона, одноцветные с вырезанным сектором
    write(OUT / 'trenio-mark.svg', svg(mark_vb,
          f'<path fill="{GRAPHITE}" d="{body}"/><path fill="{CORAL}" d="{sector}"/>'
          f'<path fill="{GRAPHITE}" d="{dot}"/>'))
    write(OUT / 'trenio-mark-white.svg', svg(mark_vb,
          f'<path fill="{WHITE}" d="{body}"/><path fill="{CORAL}" d="{sector}"/>'
          f'<path fill="{WHITE}" d="{dot}"/>'))
    for name, color in [('mono-dark', GRAPHITE), ('mono-light', WHITE)]:
        write(OUT / f'trenio-mark-{name}.svg', svg(mark_vb, mono(color, body, sector, dot)))

    # Слово trenio
    word, word_sector, width, top = word_paths(font_path)
    pad = 10
    word_vb = f'{f(-pad)} {f(-top - pad)} {f(width + 2 * pad)} {f(top + 2 * pad)}'
    for name, ink in [('', GRAPHITE), ('-white', WHITE)]:
        write(OUT / f'trenio-wordmark{name}.svg', svg(word_vb,
              f'<path fill="{ink}" d="{word}"/><path fill="{CORAL}" d="{word_sector}"/>'))
    for name, ink in [('mono-dark', GRAPHITE), ('mono-light', WHITE)]:
        write(OUT / f'trenio-wordmark-{name}.svg', svg(word_vb, mono(ink, word, word_sector)))

    # Аватарка бота: цветной знак на светлом фоне, Telegram обрежет её в круг
    place = 'translate(320 316) scale(4.1) translate(-50 -50)'
    write(OUT / 'bot-avatar.svg', svg('0 0 640 640',
          f'<rect width="640" height="640" fill="{CONCRETE}"/>'
          f'<g transform="{place}"><path fill="{GRAPHITE}" d="{body}"/>'
          f'<path fill="{CORAL}" d="{sector}"/><path fill="{GRAPHITE}" d="{dot}"/></g>'))

    # Иконка приложения: графитовый квадрат, белый секундомер
    place = 'translate(512 506) scale(6.4) translate(-50 -50)'
    write(OUT / 'app-icon.svg', svg('0 0 1024 1024',
          f'<rect width="1024" height="1024" fill="{GRAPHITE}"/>'
          f'<g transform="{place}"><path fill="{WHITE}" d="{body}"/>'
          f'<path fill="{CORAL}" d="{sector}"/><path fill="{WHITE}" d="{dot}"/></g>'))

    # Картинка в описании бота, 640×360: цветное слово на светлом фоне
    scale = 400 / width
    write(OUT / 'bot-description.svg', svg('0 0 640 360',
          f'<rect width="640" height="360" fill="{CONCRETE}"/>'
          f'<g transform="translate({f(320 - width * scale / 2)} {f(180 + top * scale / 2)}) scale({f(scale)})">'
          f'<path fill="{GRAPHITE}" d="{word}"/><path fill="{CORAL}" d="{word_sector}"/></g>'))

    # Фавиконка Mini App: в тёмной теме браузера корпус становится белым
    write(PUBLIC / 'favicon.svg', svg(mark_vb,
          '<style>.b{fill:%s}@media (prefers-color-scheme:dark){.b{fill:%s}}</style>'
          '<path class="b" d="%s"/><path fill="%s" d="%s"/><path class="b" d="%s"/>'
          % (GRAPHITE, WHITE, body, CORAL, sector, dot)))


if __name__ == '__main__':
    main(sys.argv[1])
