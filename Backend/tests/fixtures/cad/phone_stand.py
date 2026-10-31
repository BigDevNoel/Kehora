# A phone stand: base plate, a back rest tilted 70 degrees and a front lip.
from build123d import Align, Axis, Box, BuildPart, Locations, Rotation, fillet

WIDTH, DEPTH, THICK = 80.0, 90.0, 4.0

with BuildPart() as stand:
    Box(WIDTH, DEPTH, THICK, align=(Align.CENTER, Align.MIN, Align.MIN))
    with Locations((0, 4, THICK)):
        Box(WIDTH, 4, 12, align=(Align.CENTER, Align.MIN, Align.MIN))
    with Locations((0, 40, 0)):
        rest = Box(WIDTH, THICK, 100, align=(Align.CENTER, Align.MIN, Align.MIN), rotation=Rotation(-20, 0, 0))
    fillet(stand.edges().filter_by(Axis.X).group_by(Axis.Z)[-1], radius=1.5)

result = stand
