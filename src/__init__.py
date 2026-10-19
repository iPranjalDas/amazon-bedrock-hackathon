# //PRANJAL DAS
"""
Sentinel+ (Autonomous Infrastructure & Code Sentry for Alexa+)
Fusing architectural patterns from top Amazon and AWS hackathon champions.
"""
import sys
from pathlib import Path

# Ensure Drive D packages directory is on sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent
_PACKAGES_DIR = _REPO_ROOT / "packages"

if _PACKAGES_DIR.exists() and str(_PACKAGES_DIR) not in sys.path:
    sys.path.insert(0, str(_PACKAGES_DIR))

__version__ = "1.0.0"
