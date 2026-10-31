# Hexagon 100 mm corner to corner, 5 mm tall, with a 2 mm rim around a recessed top.
from build123d import Pos, RegularPolygon, extrude

body = extrude(RegularPolygon(50, 6), amount=5)
recess = Pos(0, 0, 2) * extrude(RegularPolygon(47, 6), amount=3)

result = body - recess
