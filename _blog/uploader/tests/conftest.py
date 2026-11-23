import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# 코스형 게이트·조립기·팩트 게이트는 neo_tools 에 있다(검문소와 같은 폴더).
NEO = ROOT.parent / "neo_tools"
if str(NEO) not in sys.path:
    sys.path.insert(0, str(NEO))
