"""Isolated manual QA server; never opens the development databridge.db."""
import os
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
qa_db = root / "scratch" / "m12-qa.sqlite"
os.environ["DATABASE_URL"] = f"sqlite:///{qa_db.as_posix()}"
os.environ["FRONTEND_URL"] = "http://localhost:5174"
os.environ["CORS_ORIGINS"] = '["http://localhost:5174"]'
os.environ["UPLOAD_DIR"] = str(root / "uploads" / "m12-qa")
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine

engine = create_engine(os.environ["DATABASE_URL"])
with engine.connect() as connection:
    config = Config(str(root / "alembic.ini"))
    config.attributes["connection"] = connection
    command.upgrade(config, "head")
    connection.commit()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8001)
