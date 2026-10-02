"""Initial migration for users, risk_settings, instruments, strategy_profiles, analysis_sessions, analysis_results, and trade_plans.

Revision ID: 001_initial
Revises: 
Create Date: 2026-09-28 14:25:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. users
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)

    # 2. risk_settings
    op.create_table(
        'risk_settings',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('account_balance', sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column('risk_percent', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('max_exposure_percent', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('min_risk_reward', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id')
    )

    # 3. instruments
    op.create_table(
        'instruments',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('symbol', sa.String(length=32), nullable=False),
        sa.Column('display_name', sa.String(length=128), nullable=False),
        sa.Column('category', sa.String(length=32), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_instruments_symbol'), 'instruments', ['symbol'], unique=True)

    # 4. strategy_profiles
    op.create_table(
        'strategy_profiles',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=32), nullable=False),
        sa.Column('timeframes', sa.ARRAY(sa.String(length=8)), nullable=False),
        sa.Column('min_risk_reward', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('news_sensitivity', sa.String(length=16), nullable=False),
        sa.Column('holding_period_description', sa.String(length=128), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )

    # 5. analysis_sessions
    op.create_table(
        'analysis_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('instrument_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('strategy_profile_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('requested_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='pending'),
        sa.ForeignKeyConstraint(['instrument_id'], ['instruments.id'], ),
        sa.ForeignKeyConstraint(['strategy_profile_id'], ['strategy_profiles.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_analysis_sessions_user_id'), 'analysis_sessions', ['user_id'], unique=False)

    # 6. analysis_results
    op.create_table(
        'analysis_results',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('analysis_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('ai_provider', sa.String(length=32), nullable=False),
        sa.Column('model_name', sa.String(length=64), nullable=False),
        sa.Column('raw_llm_response', sa.Text(), nullable=False),
        sa.Column('validated_schema_output', postgresql.JSONB(), nullable=True),
        sa.Column('validation_status', sa.String(length=16), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['analysis_id'], ['analysis_sessions.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_analysis_results_analysis_id'), 'analysis_results', ['analysis_id'], unique=False)

    # 7. trade_plans
    op.create_table(
        'trade_plans',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('analysis_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('bias', sa.String(length=16), nullable=False),
        sa.Column('entry', sa.Numeric(precision=18, scale=5), nullable=True),
        sa.Column('stop_loss', sa.Numeric(precision=18, scale=5), nullable=True),
        sa.Column('take_profit_1', sa.Numeric(precision=18, scale=5), nullable=True),
        sa.Column('take_profit_2', sa.Numeric(precision=18, scale=5), nullable=True),
        sa.Column('take_profit_3', sa.Numeric(precision=18, scale=5), nullable=True),
        sa.Column('risk_reward_ratio', sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column('invalidation_condition', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='WAITING'),
        sa.Column('no_trade_reason', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['analysis_id'], ['analysis_sessions.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_trade_plans_analysis_id'), 'trade_plans', ['analysis_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_trade_plans_analysis_id'), table_name='trade_plans')
    op.drop_table('trade_plans')
    op.drop_index(op.f('ix_analysis_results_analysis_id'), table_name='analysis_results')
    op.drop_table('analysis_results')
    op.drop_index(op.f('ix_analysis_sessions_user_id'), table_name='analysis_sessions')
    op.drop_table('analysis_sessions')
    op.drop_table('strategy_profiles')
    op.drop_index(op.f('ix_instruments_symbol'), table_name='instruments')
    op.drop_table('instruments')
    op.drop_table('risk_settings')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
