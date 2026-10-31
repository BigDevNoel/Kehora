# 120 mm square board, 6 x 6 grid of 5 mm peg holes (5.3 mm for fit) at 18 mm pitch.
from build123d import Align, Box, Cylinder, GridLocations, Pos

UP = (Align.CENTER, Align.CENTER, Align.MIN)

board = Box(120, 120, 8, align=UP)
holes = [Pos(0, 0, 2) * loc * Cylinder(2.65, 6, align=UP) for loc in GridLocations(18, 18, 6, 6)]

result = board - holes
