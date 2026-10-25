# Match strategy

`manager.py` controls the phases and quotas:

- Construction ends when **both** `ceil(map area / BASE_TARGET_AREA)` bases and
  `ceil(map area / WORKER_TARGET_AREA)` workers exist, or at
  `ceil(maxTurns * CONSTRUCTION_FRACTION)`. Defaults are 100, 250, and 3/5.
- Construction workers collect either ore and trade carried gold into iron in
  batches of three. Two workers cover the center and its three-tile buffer;
  others patrol separate outside arcs, normally two tiles from the wall.
- Mining stops construction and recruitment, converts carried iron into gold,
  and expands the outside workers' searches inward through their separate
  sectors. Two workers continue searching the center and its buffer.
- Each worker enters Ending based on its own travel time home, current cooldown,
  conversion time, deposit action, and `ENDING_RETURN_BUFFER` (two turns).
  `ENDING_MIN_TURNS` is three. Returning workers stop collecting, deposit at a
  friendly base, and stay there. Return estimates are recalculated each turn;
  newly revealed obstacles can still affect arrival time.

`base_planner.py` scores known open terrain and nearby ore; mountains, craters,
unknown land, and enemy claims contribute no value. It favors large unserved
gaps, with `BASE_SPACING = 10` as the outside minimum. The center gets two bases,
then an optional third after outside expansion. Targets persist during travel
and are replaced if they become unusable. The first few workers get priority;
after that, builders reserve six iron each before remaining funds recruit more
workers. Growing the base network also raises the minimum worker count to save
for, preventing bases from consuming all recruitment funds.

The quotas on a 50×50 map are 25 bases and 10 workers. Construction ends when
both targets are met or the time cutoff is reached. The quotas are caps/phase
targets, not a reason to crowd bases together.

Validation: `python -m unittest discover -s tests`. Tests include terrain-aware
placement, budgets, sector ownership, patrol movement, conversion, and banking
deadlines. Action exports alone do not include enough world state to reproduce
a match or establish a score improvement.
