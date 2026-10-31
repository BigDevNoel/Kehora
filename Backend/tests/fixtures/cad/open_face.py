# A single face, not a solid: the harness must report "no solid" before exporting.
from build123d import Plane, Rectangle

result = Plane.XY * Rectangle(20, 20).face()
