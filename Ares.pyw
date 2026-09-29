# Double-click to start ARES with no terminal window (.pyw runs under pythonw.exe).
import os
import sys
import runpy
from pathlib import Path

HERE = Path(__file__).resolve().parent
os.chdir(HERE)
sys.path.insert(0, str(HERE))
sys.argv = [str(HERE / "ares_companion.py")] + sys.argv[1:]
runpy.run_path(str(HERE / "ares_companion.py"), run_name="__main__")
