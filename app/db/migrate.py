from pathlib import Path

from alembic import command
from alembic.config import Config


def run_migrations() -> None:
    """Apply pending Alembic migrations (additive; safe after create_all)."""
    root = Path(__file__).resolve().parents[2]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    command.upgrade(cfg, "head")
