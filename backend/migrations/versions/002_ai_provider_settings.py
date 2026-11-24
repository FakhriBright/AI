"""Add per-user AI provider settings.

Revision ID: 002_ai_provider_settings
Revises: 001_initial
Create Date: 2026-11-24 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '002_ai_provider_settings'
down_revision = '001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'ai_provider_settings',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('provider', sa.String(length=32), nullable=False),
        sa.Column('model_by_provider', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('auto_switch', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('fallback_order', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id')
    )


def downgrade() -> None:
    op.drop_table('ai_provider_settings')
