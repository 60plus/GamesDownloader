"""Padlock on a game's or a ROM's metadata.

Closed means only an administrator may change it. Set from the padlock in the
corner of the metadata editor, and read as a permission rather than enforced as
a guard on writes, so the passes that run without a person behind them are not
affected by it.

Not nullable, and defaulted to open. A NULL here would have to be read as one
or the other, and reading it as closed would freeze every existing game the
moment the column arrived.
"""
from alembic import op
import sqlalchemy as sa

revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ('library_games', 'roms'):
        op.add_column(table, sa.Column(
            'metadata_locked', sa.Boolean(), nullable=False, server_default=sa.text('0'),
        ))


def downgrade() -> None:
    op.drop_column('roms', 'metadata_locked')
    op.drop_column('library_games', 'metadata_locked')
