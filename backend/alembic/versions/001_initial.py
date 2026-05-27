"""Initial schema

Revision ID: 001_initial
Revises:
Create Date: 2025-05-18
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision      = '001_initial'
down_revision = None
branch_labels = None
depends_on    = None


def upgrade():
    op.create_table('users',
        sa.Column('id',               sa.Integer(),     primary_key=True),
        sa.Column('email',            sa.String(255),   nullable=False),
        sa.Column('hashed_password',  sa.String(255),   nullable=False),
        sa.Column('full_name',        sa.String(255),   nullable=False),
        sa.Column('phone',            sa.String(20),    nullable=True),
        sa.Column('is_active',        sa.Boolean(),     server_default='true',  nullable=False),
        sa.Column('is_admin',         sa.Boolean(),     server_default='false', nullable=False),
        sa.Column('created_at',       sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True)

    op.create_table('cameras',
        sa.Column('id',             sa.Integer(),    primary_key=True),
        sa.Column('name',           sa.String(100),  nullable=False),
        sa.Column('rtsp_url',       sa.String(500),  nullable=False),
        sa.Column('site_id',        sa.Integer(),    nullable=False),
        sa.Column('zone',           sa.String(100),  nullable=True),
        sa.Column('location_label', sa.String(200),  nullable=True),
        sa.Column('gps_coords',     sa.JSON(),       nullable=True),
        sa.Column('status',         sa.String(20),   server_default='offline', nullable=False),
        sa.Column('config',         sa.JSON(),       nullable=True),
        sa.Column('is_active',      sa.Boolean(),    server_default='true', nullable=False),
        sa.Column('last_seen',      sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at',     sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_cameras_site_id', 'cameras', ['site_id'])

    op.create_table('violations',
        sa.Column('id',               sa.Integer(),  primary_key=True),
        sa.Column('camera_id',        sa.Integer(),  sa.ForeignKey('cameras.id'), nullable=False),
        sa.Column('violation_type',   sa.String(50), nullable=False),
        sa.Column('confidence',       sa.Float(),    nullable=False),
        sa.Column('severity',         sa.String(20), nullable=False),
        sa.Column('bounding_box',     sa.JSON(),     nullable=True),
        sa.Column('frame_detections', sa.JSON(),     nullable=True),
        sa.Column('snapshot_path',    sa.String(500), nullable=True),
        sa.Column('worker_id',        sa.String(100), nullable=True),
        sa.Column('zone_label',       sa.String(100), nullable=True),
        sa.Column('acknowledged',     sa.Boolean(),   server_default='false', nullable=False),
        sa.Column('acknowledged_by',  sa.Integer(),   sa.ForeignKey('users.id'), nullable=True),
        sa.Column('acknowledged_at',  sa.DateTime(timezone=True), nullable=True),
        sa.Column('timestamp',        sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_violations_camera_id',     'violations', ['camera_id'])
    op.create_index('ix_violations_violation_type','violations', ['violation_type'])
    op.create_index('ix_violations_timestamp',     'violations', ['timestamp'])
    op.create_index('ix_violations_camera_ts',     'violations', ['camera_id', 'timestamp'])

    op.create_table('alerts',
        sa.Column('id',                sa.Integer(),  primary_key=True),
        sa.Column('violation_id',      sa.Integer(),  sa.ForeignKey('violations.id'), nullable=False),
        sa.Column('camera_id',         sa.Integer(),  sa.ForeignKey('cameras.id'),    nullable=False),
        sa.Column('recipient_user_id', sa.Integer(),  sa.ForeignKey('users.id'),      nullable=True),
        sa.Column('recipient_phone',   sa.String(20), nullable=False),
        sa.Column('status',            sa.String(20), server_default='pending', nullable=False),
        sa.Column('twilio_sid',        sa.String(100), nullable=True),
        sa.Column('error_message',     sa.Text(),     nullable=True),
        sa.Column('message_body',      sa.Text(),     nullable=False),
        sa.Column('sent_at',           sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at',        sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_alerts_violation_id', 'alerts', ['violation_id'])

    op.create_table('compliance_reports',
        sa.Column('id',           sa.Integer(),  primary_key=True),
        sa.Column('site_id',      sa.Integer(),  nullable=False),
        sa.Column('report_date',  sa.DateTime(timezone=True), nullable=False),
        sa.Column('period',       sa.String(20), nullable=False),
        sa.Column('summary',      sa.JSON(),     nullable=True),
        sa.Column('pdf_path',     sa.String(500), nullable=True),
        sa.Column('generated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('generated_by', sa.Integer(),  sa.ForeignKey('users.id'), nullable=True),
    )
    op.create_index('ix_compliance_reports_site_id',     'compliance_reports', ['site_id'])
    op.create_index('ix_compliance_reports_report_date', 'compliance_reports', ['report_date'])


def downgrade():
    op.drop_table('compliance_reports')
    op.drop_table('alerts')
    op.drop_table('violations')
    op.drop_table('cameras')
    op.drop_table('users')
