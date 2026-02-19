# This file helps Pylance and other IDEs resolve imports from the shared module
import sys
from pathlib import Path

# Add shared directory to path for IDE resolution
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "shared"))
