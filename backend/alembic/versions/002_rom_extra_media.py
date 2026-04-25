"""Add extra media columns to roms table

Revision ID: 002
Revises: 001
Create Date: 2026-03-29
"""
from alembic import op
import sqlalchemy as sa

revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('roms', sa.Column('support_path',   sa.String(512), nullable=True))
    op.add_column('roms', sa.Column('wheel_path',     sa.String(512), nullable=True))
    op.add_column('roms', sa.Column('bezel_path',     sa.String(512), nullable=True))
    op.add_column('roms', sa.Column('steamgrid_path', sa.String(512), nullable=True))
    op.add_column('roms', sa.Column('video_path',     sa.String(512), nullable=True))


def downgrade() -> None:
    op.drop_column('roms', 'video_path')
    op.drop_column('roms', 'steamgrid_path')
    op.drop_column('roms', 'bezel_path')
    op.drop_column('roms', 'wheel_path')
    op.drop_column('roms', 'support_path')
