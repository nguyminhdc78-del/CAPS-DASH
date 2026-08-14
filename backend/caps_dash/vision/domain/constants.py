"""Tuning constants for slot assignment.

Fixed by the problem rather than by preference, so they live here and not in
application settings. The notes record what was already tried.
"""

from __future__ import annotations

# Fraction of the bottom-band sample points that must fall inside a polygon
# for the fallback assignment step to accept it.
#
# 0.40 tolerates a slot drawn short by roughly 20% of a vehicle's height while
# still refusing a car that merely clips the edge. Raising it to 0.60 makes a
# hit too hard to earn; dropping to 0.20 starts claiming the neighbour's car.
MIN_BAND_COVERAGE = 0.40

# Bottom fraction of a bounding box used for that sampling, and the grid size.
BAND_FRACTION = 0.30
BAND_COLS = 5
BAND_ROWS = 5

# Above this IoU, two boxes in the same slot are one vehicle detected twice
# rather than two vehicles parked in it.
#
# A stock COCO model routinely returns the same car as both "car" and "truck",
# and the export used here runs NMS inside the graph per class, so those
# duplicates survive into the detection list. Counting them as separate
# vehicles fired the "polygon drawn across two rows" warning 25 times in 45
# minutes on a rig holding three cars, which is how the install-time
# diagnostic became noise. 0.50 is deliberately looser than the 0.45 used for
# NMS: these boxes have already survived it.
SAME_VEHICLE_IOU = 0.50

# Default temporal-vote settings. Per-camera overrides live in the database.
#
# The reference deployment's own configuration notes record that a 1.0s poll
# with a 3-vote threshold flickered constantly, because detector confidence
# oscillates around the acceptance threshold, and that a real installation
# wants roughly 3.0s x 4 - about twelve seconds for a slot to settle.
DEFAULT_VOTE_WINDOW = 5
DEFAULT_VOTE_THRESHOLD = 4
