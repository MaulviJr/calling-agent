"""Per-business calendar connections."""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"


def upgrade():
    op.create_table('calendar_connections',
        sa.Column('business_id', sa.String(length=32), nullable=False),
        sa.Column('provider', sa.String(length=20), nullable=False, server_default='google'),
        sa.Column('calendar_id', sa.String(length=254), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='unchecked'),
        sa.Column('last_checked_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['business_id'], ['businesses.id']),
        sa.PrimaryKeyConstraint('business_id'),
        sa.UniqueConstraint('calendar_id'),
    )


def downgrade():
    op.drop_table('calendar_connections')