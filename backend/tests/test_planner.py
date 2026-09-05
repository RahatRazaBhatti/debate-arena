import sys
from pathlib import Path

# Add project root to Python path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from arena.research_planner import ResearchPlanner

planner = ResearchPlanner()

plan = planner.create_plan(
    topic="Should Homework Be Banned",
    speaker="Elena",
    opponent_argument="Homework improves grades",
    strategy="Attack the evidence",
    argument_memory="",
)

print(plan)