from build123d import Align, Cylinder

UP = (Align.CENTER, Align.CENTER, Align.MIN)

result = Cylinder(6, 10, align=UP) - Cylinder(2.75, 10, align=UP)  # 5.5 mm clearance bore
