"""Initial schema — все таблицы создаются из метаданных моделей.

Revision ID: 0001
Revises:
Create Date: 2026-08-06
"""
from alembic import op

from app.db.models import Base

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind)
