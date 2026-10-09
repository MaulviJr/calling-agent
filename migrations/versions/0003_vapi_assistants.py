"""Assistant to business mapping."""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"


def upgrade():
    op.create_table('vapi_assistants',
        sa.Column('assistant_id', sa.String(length=120), nullable=False),
        sa.Column('business_id', sa.String(length=32), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['business_id'], ['businesses.id']),
        sa.PrimaryKeyConstraint('assistant_id'),
    )
    op.create_index(op.f('ix_vapi_assistants_business_id'), 'vapi_assistants', ['business_id'])


def downgrade():
    op.drop_index(op.f('ix_vapi_assistants_business_id'), table_name='vapi_assistants')
    op.drop_table('vapi_assistants')