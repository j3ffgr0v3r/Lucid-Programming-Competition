# 14th Lucid Coding Competition

This repository contains our team's Python bot for the 14th Lucid Coding Competition. A central manager coordinates our rovers through shared behavior states, using remembered map information to plan routes, collect ore, build bases, and recruit workers.

Our strategy starts with construction: two rovers cover the resource-rich center while the others patrol separate outside sectors, building bases near productive terrain and filling gaps in our coverage. We convert gold into iron when needed to fund worthwhile expansion, then switch to mining once our construction targets are met or three-fifths of the match has elapsed. During mining, rovers choose deposits based on expected banked gold per turn and convert iron into gold. As the match ends, each rover heads home with enough time to deposit its cargo.
