"""Add announced_at columns for the recently-added notification

Revision ID: 003
Revises: 002
Create Date: 2026-07-11
"""
from alembic import op
import sqlalchemy as sa

revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('library_games', sa.Column('announced_at', sa.DateTime(), nullable=True))
    op.add_column('roms',          sa.Column('announced_at', sa.DateTime(), nullable=True))
    # Suppress the pre-existing library so the first deploy never floods.
    op.execute("UPDATE library_games SET announced_at = NOW()")
    op.execute("UPDATE roms SET announced_at = NOW()")


def downgrade() -> None:
    op.drop_column('roms', 'announced_at')
    op.drop_column('library_games', 'announced_at')
