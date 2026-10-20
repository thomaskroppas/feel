"""load emotions from data/emotions.json

Revision ID: 0002
Revises: 0001
"""
from alembic import op

from app.services.emotions import sync_emotions

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    sync_emotions(op.get_bind())


def downgrade() -> None:
    op.execute("DELETE FROM emotions")
