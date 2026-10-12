"""Operator overrides per assistant."""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"


def upgrade():
    op.add_column('vapi_assistants',
        sa.Column('overrides', sa.JSON(), nullable=False, server_default=sa.text("'{}'")))


def downgrade():
    op.drop_column('vapi_assistants', 'overrides')