"""Add site_config table

Revision ID: 002_site_config
Revises: 001_initial
Create Date: 2025-05-18
"""
from alembic import op
import sqlalchemy as sa

revision      = '002_site_config'
down_revision = '001_initial'
branch_labels = None
depends_on    = None


def upgrade():
    op.create_table('site_config',
        sa.Column('id',         sa.Integer(), primary_key=True),
        sa.Column('key',        sa.String(100), nullable=False),
        sa.Column('value',      sa.JSON(),      nullable=False),
        sa.Column('updated_by', sa.Integer(),   sa.ForeignKey('users.id'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_site_config_key', 'site_config', ['key'], unique=True)


def downgrade():
    op.drop_table('site_config')
