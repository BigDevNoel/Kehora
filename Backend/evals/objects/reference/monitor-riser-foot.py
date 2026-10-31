# 60 x 60 x 40 block with a 20 mm deep slot for an 18 mm board (0.4 mm clearance).
from build123d import Align, Box, Pos

UP = (Align.CENTER, Align.CENTER, Align.MIN)

result = Box(60, 60, 40, align=UP) - Pos(0, 0, 20) * Box(18.4, 60, 20, align=UP)
