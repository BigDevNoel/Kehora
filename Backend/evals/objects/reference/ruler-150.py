# 160 x 25 x 3 mm ruler with 0.4 mm wide, 0.6 mm deep ticks for 0-150 mm.
from build123d import Align, Box, Pos

ruler = Box(160, 25, 3, align=Align.MIN)
ticks = []
for mm in range(151):
    length = 10 if mm % 10 == 0 else 7 if mm % 5 == 0 else 4
    ticks.append(Pos(5 + mm - 0.2, 25 - length, 2.4) * Box(0.4, length, 0.6, align=Align.MIN))

result = ruler - ticks
