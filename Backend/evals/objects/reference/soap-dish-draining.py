# 110 x 80 mm dish, 3 mm walls, five drain slots in the floor and ribs between them.
from build123d import Align, Box, Pos

UP = (Align.CENTER, Align.CENTER, Align.MIN)

shell = Box(110, 80, 15, align=UP) - Pos(0, 0, 3) * Box(104, 74, 15, align=UP)
slots = [Pos(x, 0, 0) * Box(3, 50, 3, align=UP) for x in (-30, -15, 0, 15, 30)]
ribs = [Pos(x, 0, 3) * Box(2, 70, 3, align=UP) for x in (-37.5, -22.5, -7.5, 7.5, 22.5, 37.5)]

result = shell - slots + ribs
