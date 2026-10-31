# 20 x 20 mm adhesive base with a bridge that a 4 mm cable tie threads under.
from build123d import Align, Box, Pos

UP = (Align.CENTER, Align.CENTER, Align.MIN)

base = Box(20, 20, 3, align=UP)
bridge = Pos(0, 0, 3) * Box(8, 20, 4, align=UP)
tunnel = Pos(0, 0, 3.5) * Box(8, 5, 2, align=UP)

result = base + bridge - tunnel
