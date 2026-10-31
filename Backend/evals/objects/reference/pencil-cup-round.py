from build123d import Align, Cylinder, Pos

UP = (Align.CENTER, Align.CENTER, Align.MIN)
BASE = 3

result = Cylinder(35, 100, align=UP) - Pos(0, 0, BASE) * Cylinder(32, 100, align=UP)
