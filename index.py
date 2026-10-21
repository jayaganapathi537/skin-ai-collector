from pathlib import Path

from backend.app.main import app

app.frontend("/", directory=str(Path(__file__).resolve().parent / "dist"), fallback="index.html")
