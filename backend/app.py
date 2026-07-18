import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import create_app


app = create_app()
application = app


if __name__ == "__main__":
    app.run(debug=True)
