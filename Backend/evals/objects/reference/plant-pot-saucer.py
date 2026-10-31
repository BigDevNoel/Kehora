from build123d import Align, Cylinder, Pos

UP = (Align.CENTER, Align.CENTER, Align.MIN)

result = Cylinder(70, 15, align=UP) - Pos(0, 0, 3) * Cylinder(67, 15, align=UP)
