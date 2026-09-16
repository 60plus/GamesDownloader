"""Who brought a particular file in.

The upload quota is a sum over the games an account owns, which is right for a
game it also uploaded and wrong for every other way a file can land on one. A
catalogue entry downloaded a second time reuses the LibraryGame the first
account created - deliberately, it is the same game - so the second person's
gigabytes were counted against the first, who could be pushed over a limit by
uploads they never made.

Nullable on purpose. The sum reads this in preference to the game's owner and
falls back when it is not set, so every row that already exists keeps counting
exactly as it counts today. A NOT NULL column with a default would have had to
name somebody, and there is no right answer to name.
"""
from alembic import op
import sqlalchemy as sa

revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('library_files', sa.Column('published_by', sa.Integer(), nullable=True))
    op.create_index('ix_library_files_published_by', 'library_files', ['published_by'])


def downgrade() -> None:
    op.drop_index('ix_library_files_published_by', table_name='library_files')
    op.drop_column('library_files', 'published_by')
