# L bracket: 100 mm arms, 30 mm wide, 5 mm thick, 45 degree brace, two 4.5 mm holes per arm.
from build123d import Align, Box, Cylinder, Plane, Polygon, Pos, Rot, extrude

LOW = (Align.MIN, Align.CENTER, Align.MIN)
UP = (Align.CENTER, Align.CENTER, Align.MIN)
ARM, WIDTH, THICK, HOLE_R = 100, 30, 5, 2.25

floor = Box(ARM, WIDTH, THICK, align=LOW)
wall = Box(THICK, WIDTH, ARM, align=LOW)
brace = extrude(Plane.XZ * Polygon((THICK, THICK), (60, THICK), (THICK, 60)), amount=2.5, both=True)

floor_holes = [Pos(x, 0, 0) * Cylinder(HOLE_R, THICK, align=UP) for x in (40, 85)]
wall_holes = [Pos(0, 0, z) * Rot(0, 90, 0) * Cylinder(HOLE_R, THICK, align=UP) for z in (40, 85)]

result = floor + wall + brace - floor_holes - wall_holes
