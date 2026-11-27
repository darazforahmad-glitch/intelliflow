"""Initial schema: the 15 tables of the data dictionary (Section 4.3) plus supporting tables.

Revision ID: 0001
Revises: 
Create Date: 2026-11-27 13:41:59.108415
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0001'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('email_messages',
    sa.Column('to_address', sa.String(length=255), nullable=False),
    sa.Column('subject', sa.String(length=255), nullable=False),
    sa.Column('body_text', sa.Text(), nullable=False),
    sa.Column('category', sa.String(length=40), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_email_messages'))
    )
    op.create_index(op.f('ix_email_messages_to_address'), 'email_messages', ['to_address'], unique=False)
    op.create_table('templates',
    sa.Column('code', sa.String(length=60), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('category', sa.String(length=60), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('definition_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('match_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('required_connections', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('retired_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_templates')),
    sa.UniqueConstraint('code', 'version', name=op.f('uq_templates_code_version'))
    )
    op.create_index(op.f('ix_templates_code'), 'templates', ['code'], unique=False)
    op.create_index('uq_templates_active_code', 'templates', ['code'], unique=True, postgresql_where=sa.text('is_active'), sqlite_where=sa.text('is_active = 1'))
    op.create_table('users',
    sa.Column('full_name', sa.String(length=100), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('phone', sa.String(length=20), nullable=True),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('email_verified', sa.Boolean(), nullable=False),
    sa.Column('is_platform_admin', sa.Boolean(), nullable=False),
    sa.Column('failed_login_attempts', sa.SmallInteger(), nullable=False),
    sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('token_version', sa.Integer(), nullable=False),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users'))
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_table('workspaces',
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('business_type', sa.String(length=60), nullable=True),
    sa.Column('language_pref', sa.String(length=10), nullable=False),
    sa.Column('timezone', sa.String(length=40), nullable=False),
    sa.Column('ai_credit_limit', sa.Integer(), nullable=True),
    sa.Column('status', sa.Enum('active', 'suspended', name='workspace_status'), nullable=False),
    sa.Column('approval_threshold', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('suspended_reason', sa.Text(), nullable=True),
    sa.Column('settings_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_workspaces'))
    )
    op.create_table('audit_logs',
    sa.Column('workspace_id', sa.Uuid(), nullable=True),
    sa.Column('actor_id', sa.Uuid(), nullable=True),
    sa.Column('action', sa.String(length=80), nullable=False),
    sa.Column('entity_type', sa.String(length=40), nullable=True),
    sa.Column('entity_id', sa.String(length=64), nullable=True),
    sa.Column('data_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('ip_address', sa.String(length=45), nullable=True),
    sa.Column('request_id', sa.String(length=64), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], name=op.f('fk_audit_logs_actor_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name=op.f('fk_audit_logs_workspace_id_workspaces'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_logs'))
    )
    op.create_index('ix_audit_logs_workspace_created', 'audit_logs', ['workspace_id', 'created_at'], unique=False)
    op.create_table('connections',
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('provider', sa.Enum('whatsapp', 'gmail', 'google_sheets', 'webform', name='connection_provider'), nullable=False),
    sa.Column('external_account_id', sa.String(length=120), nullable=True),
    sa.Column('token_encrypted', sa.LargeBinary(), nullable=True),
    sa.Column('status', sa.Enum('connected', 'needs_attention', 'disconnected', name='connection_status'), nullable=False),
    sa.Column('mode', sa.Enum('live', 'sandbox', name='connection_mode'), nullable=False),
    sa.Column('display_name', sa.String(length=120), nullable=True),
    sa.Column('config_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('scopes', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('token_expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.Column('connected_by', sa.Uuid(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['connected_by'], ['users.id'], name=op.f('fk_connections_connected_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name=op.f('fk_connections_workspace_id_workspaces'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_connections'))
    )
    op.create_index(op.f('ix_connections_external_account_id'), 'connections', ['external_account_id'], unique=False)
    op.create_index(op.f('ix_connections_workspace_id'), 'connections', ['workspace_id'], unique=False)
    op.create_table('interview_sessions',
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('started_by', sa.Uuid(), nullable=True),
    sa.Column('process_name', sa.String(length=120), nullable=False),
    sa.Column('status', sa.Enum('in_progress', 'completed', 'abandoned', name='interview_status'), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('question_count', sa.SmallInteger(), nullable=False),
    sa.Column('language', sa.String(length=10), nullable=True),
    sa.Column('ready_for_mapping', sa.Boolean(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['started_by'], ['users.id'], name=op.f('fk_interview_sessions_started_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name=op.f('fk_interview_sessions_workspace_id_workspaces'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_interview_sessions'))
    )
    op.create_index(op.f('ix_interview_sessions_workspace_id'), 'interview_sessions', ['workspace_id'], unique=False)
    op.create_table('invitations',
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('role', sa.Enum('owner', 'staff', name='membership_role'), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('invited_by', sa.Uuid(), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['invited_by'], ['users.id'], name=op.f('fk_invitations_invited_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name=op.f('fk_invitations_workspace_id_workspaces'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_invitations')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_invitations_token_hash'))
    )
    op.create_index(op.f('ix_invitations_workspace_id'), 'invitations', ['workspace_id'], unique=False)
    op.create_table('llm_usage',
    sa.Column('workspace_id', sa.Uuid(), nullable=True),
    sa.Column('task', sa.String(length=40), nullable=False),
    sa.Column('provider', sa.String(length=20), nullable=False),
    sa.Column('model', sa.String(length=60), nullable=False),
    sa.Column('input_tokens', sa.Integer(), nullable=False),
    sa.Column('output_tokens', sa.Integer(), nullable=False),
    sa.Column('cost_usd', sa.Numeric(precision=10, scale=6), nullable=False),
    sa.Column('credits', sa.Integer(), nullable=False),
    sa.Column('succeeded', sa.Boolean(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name=op.f('fk_llm_usage_workspace_id_workspaces'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_llm_usage'))
    )
    op.create_index('ix_llm_usage_workspace_created', 'llm_usage', ['workspace_id', 'created_at'], unique=False)
    op.create_table('memberships',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('role', sa.Enum('owner', 'staff', name='membership_role'), nullable=False),
    sa.Column('status', sa.Enum('invited', 'active', 'removed', name='membership_status'), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_memberships_user_id_users'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name=op.f('fk_memberships_workspace_id_workspaces'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_memberships')),
    sa.UniqueConstraint('user_id', 'workspace_id', name=op.f('uq_memberships_user_id_workspace_id'))
    )
    op.create_index(op.f('ix_memberships_user_id'), 'memberships', ['user_id'], unique=False)
    op.create_index(op.f('ix_memberships_workspace_id'), 'memberships', ['workspace_id'], unique=False)
    op.create_table('notifications',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=True),
    sa.Column('kind', sa.String(length=40), nullable=False),
    sa.Column('title', sa.String(length=150), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('url', sa.String(length=255), nullable=True),
    sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_notifications_user_id_users'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name=op.f('fk_notifications_workspace_id_workspaces'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_notifications'))
    )
    op.create_index('ix_notifications_user_created', 'notifications', ['user_id', 'created_at'], unique=False)
    op.create_table('push_subscriptions',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('endpoint', sa.Text(), nullable=False),
    sa.Column('p256dh', sa.String(length=255), nullable=False),
    sa.Column('auth', sa.String(length=255), nullable=False),
    sa.Column('user_agent', sa.String(length=255), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_push_subscriptions_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_push_subscriptions')),
    sa.UniqueConstraint('endpoint', name=op.f('uq_push_subscriptions_endpoint'))
    )
    op.create_index(op.f('ix_push_subscriptions_user_id'), 'push_subscriptions', ['user_id'], unique=False)
    op.create_table('user_tokens',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('purpose', sa.Enum('verify_email', 'reset_password', name='token_purpose'), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_user_tokens_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_user_tokens')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_user_tokens_token_hash'))
    )
    op.create_index(op.f('ix_user_tokens_user_id'), 'user_tokens', ['user_id'], unique=False)
    op.create_table('interview_messages',
    sa.Column('session_id', sa.Uuid(), nullable=False),
    sa.Column('sender', sa.Enum('ai', 'user', name='message_sender'), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('language', sa.String(length=10), nullable=True),
    sa.Column('meta_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['session_id'], ['interview_sessions.id'], name=op.f('fk_interview_messages_session_id_interview_sessions'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_interview_messages'))
    )
    op.create_index(op.f('ix_interview_messages_session_id'), 'interview_messages', ['session_id'], unique=False)
    op.create_table('process_maps',
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('session_id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('graph_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('change_note', sa.String(length=255), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_process_maps_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['session_id'], ['interview_sessions.id'], name=op.f('fk_process_maps_session_id_interview_sessions'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name=op.f('fk_process_maps_workspace_id_workspaces'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_process_maps')),
    sa.UniqueConstraint('session_id', 'version', name=op.f('uq_process_maps_session_id_version'))
    )
    op.create_index(op.f('ix_process_maps_session_id'), 'process_maps', ['session_id'], unique=False)
    op.create_index(op.f('ix_process_maps_workspace_id'), 'process_maps', ['workspace_id'], unique=False)
    op.create_table('sandbox_records',
    sa.Column('connection_id', sa.Uuid(), nullable=False),
    sa.Column('resource', sa.String(length=120), nullable=False),
    sa.Column('row_number', sa.Integer(), nullable=True),
    sa.Column('data_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['connection_id'], ['connections.id'], name=op.f('fk_sandbox_records_connection_id_connections'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sandbox_records'))
    )
    op.create_index(op.f('ix_sandbox_records_connection_id'), 'sandbox_records', ['connection_id'], unique=False)
    op.create_table('process_steps',
    sa.Column('map_id', sa.Uuid(), nullable=False),
    sa.Column('seq_no', sa.SmallInteger(), nullable=False),
    sa.Column('title', sa.String(length=150), nullable=False),
    sa.Column('step_type', sa.Enum('start', 'manual', 'automated', 'human_only', 'end', name='step_type'), nullable=False),
    sa.Column('minutes_per_run', sa.Numeric(precision=6, scale=1), nullable=True),
    sa.Column('runs_per_week', sa.Integer(), nullable=True),
    sa.Column('is_manual', sa.Boolean(), nullable=False),
    sa.Column('step_key', sa.String(length=30), nullable=False),
    sa.Column('actor', sa.String(length=80), nullable=True),
    sa.Column('action', sa.Text(), nullable=True),
    sa.Column('app', sa.String(length=40), nullable=True),
    sa.Column('predecessor_key', sa.String(length=30), nullable=True),
    sa.Column('involves_customer_messaging', sa.Boolean(), nullable=False),
    sa.Column('involves_money', sa.Boolean(), nullable=False),
    sa.Column('support_status', sa.String(length=20), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['map_id'], ['process_maps.id'], name=op.f('fk_process_steps_map_id_process_maps'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_process_steps')),
    sa.UniqueConstraint('map_id', 'seq_no', name=op.f('uq_process_steps_map_id_seq_no')),
    sa.UniqueConstraint('map_id', 'step_key', name=op.f('uq_process_steps_map_id_step_key'))
    )
    op.create_index(op.f('ix_process_steps_map_id'), 'process_steps', ['map_id'], unique=False)
    op.create_table('opportunities',
    sa.Column('map_id', sa.Uuid(), nullable=False),
    sa.Column('step_id', sa.Uuid(), nullable=False),
    sa.Column('template_id', sa.Uuid(), nullable=True),
    sa.Column('rank', sa.SmallInteger(), nullable=True),
    sa.Column('score', sa.Numeric(precision=8, scale=2), nullable=False),
    sa.Column('status', sa.Enum('suggested', 'selected', 'dismissed', 'automated', name='opportunity_status'), nullable=False),
    sa.Column('fit', sa.Numeric(precision=3, scale=2), nullable=False),
    sa.Column('risk', sa.Numeric(precision=3, scale=2), nullable=False),
    sa.Column('minutes_saved_per_week', sa.Numeric(precision=8, scale=1), nullable=False),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['map_id'], ['process_maps.id'], name=op.f('fk_opportunities_map_id_process_maps'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['step_id'], ['process_steps.id'], name=op.f('fk_opportunities_step_id_process_steps'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['template_id'], ['templates.id'], name=op.f('fk_opportunities_template_id_templates'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_opportunities'))
    )
    op.create_index(op.f('ix_opportunities_map_id'), 'opportunities', ['map_id'], unique=False)
    op.create_table('automations',
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('opportunity_id', sa.Uuid(), nullable=True),
    sa.Column('current_version_id', sa.Uuid(), nullable=True),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('status', sa.Enum('draft', 'validated', 'tested', 'active', 'paused', 'error', 'archived', name='automation_status'), nullable=False),
    sa.Column('template_id', sa.Uuid(), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('trigger_type', sa.String(length=60), nullable=True),
    sa.Column('estimated_minutes_per_run', sa.Numeric(precision=6, scale=1), nullable=False),
    sa.Column('auto_send', sa.Boolean(), nullable=False),
    sa.Column('consecutive_failures', sa.SmallInteger(), nullable=False),
    sa.Column('status_reason', sa.Text(), nullable=True),
    sa.Column('activated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_automations_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['opportunity_id'], ['opportunities.id'], name=op.f('fk_automations_opportunity_id_opportunities'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['template_id'], ['templates.id'], name=op.f('fk_automations_template_id_templates'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name=op.f('fk_automations_workspace_id_workspaces'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_automations'))
    )
    op.create_index(op.f('ix_automations_trigger_type'), 'automations', ['trigger_type'], unique=False)
    op.create_index(op.f('ix_automations_workspace_id'), 'automations', ['workspace_id'], unique=False)
    op.create_table('automation_versions',
    sa.Column('automation_id', sa.Uuid(), nullable=False),
    sa.Column('version_no', sa.Integer(), nullable=False),
    sa.Column('definition_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('validated', sa.Boolean(), nullable=False),
    sa.Column('test_passed', sa.Boolean(), nullable=False),
    sa.Column('validation_errors', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('source', sa.String(length=20), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['automation_id'], ['automations.id'], name=op.f('fk_automation_versions_automation_id_automations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_automation_versions_created_by_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_automation_versions')),
    sa.UniqueConstraint('automation_id', 'version_no', name=op.f('uq_automation_versions_automation_id_version_no'))
    )
    op.create_index(op.f('ix_automation_versions_automation_id'), 'automation_versions', ['automation_id'], unique=False)
    # automations <-> automation_versions reference each other: add this FK last.
    # Batch mode: a plain ALTER on PostgreSQL, copy-and-move on SQLite.
    with op.batch_alter_table('automations') as batch:
        batch.create_foreign_key(op.f('fk_automations_current_version_id_automation_versions'),
                                 'automation_versions', ['current_version_id'], ['id'], ondelete='SET NULL')
    op.create_table('runs',
    sa.Column('automation_id', sa.Uuid(), nullable=False),
    sa.Column('version_id', sa.Uuid(), nullable=False),
    sa.Column('event_id', sa.String(length=120), nullable=False),
    sa.Column('status', sa.Enum('queued', 'running', 'waiting_approval', 'succeeded', 'failed', 'cancelled', name='run_status'), nullable=False),
    sa.Column('minutes_saved', sa.Numeric(precision=6, scale=1), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('is_test', sa.Boolean(), nullable=False),
    sa.Column('trigger_type', sa.String(length=60), nullable=False),
    sa.Column('resume_point', sa.SmallInteger(), nullable=False),
    sa.Column('context_encrypted', sa.LargeBinary(), nullable=True),
    sa.Column('summary', sa.Text(), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['automation_id'], ['automations.id'], name=op.f('fk_runs_automation_id_automations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['version_id'], ['automation_versions.id'], name=op.f('fk_runs_version_id_automation_versions')),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name=op.f('fk_runs_workspace_id_workspaces'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_runs')),
    sa.UniqueConstraint('automation_id', 'event_id', name=op.f('uq_runs_automation_id_event_id'))
    )
    op.create_index(op.f('ix_runs_automation_id'), 'runs', ['automation_id'], unique=False)
    op.create_index('ix_runs_workspace_created', 'runs', ['workspace_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_runs_workspace_id'), 'runs', ['workspace_id'], unique=False)
    op.create_table('step_runs',
    sa.Column('run_id', sa.Uuid(), nullable=False),
    sa.Column('step_key', sa.String(length=60), nullable=False),
    sa.Column('status', sa.Enum('running', 'succeeded', 'failed', 'skipped', 'waiting', name='step_run_status'), nullable=False),
    sa.Column('input_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True),
    sa.Column('output_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True),
    sa.Column('attempt', sa.SmallInteger(), nullable=False),
    sa.Column('seq_no', sa.SmallInteger(), nullable=False),
    sa.Column('block_type', sa.String(length=40), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['run_id'], ['runs.id'], name=op.f('fk_step_runs_run_id_runs'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_step_runs')),
    sa.UniqueConstraint('run_id', 'step_key', name=op.f('uq_step_runs_run_id_step_key'))
    )
    op.create_index(op.f('ix_step_runs_run_id'), 'step_runs', ['run_id'], unique=False)
    op.create_table('approval_tasks',
    sa.Column('step_run_id', sa.Uuid(), nullable=False),
    sa.Column('assignee_id', sa.Uuid(), nullable=True),
    sa.Column('decided_by', sa.Uuid(), nullable=True),
    sa.Column('payload_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('status', sa.Enum('pending', 'reminded', 'approved', 'edited', 'rejected', 'expired', name='approval_status'), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('run_id', sa.Uuid(), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('automation_id', sa.Uuid(), nullable=False),
    sa.Column('kind', sa.Enum('customer_message', 'money', 'review', 'window_closed', name='approval_kind'), nullable=False),
    sa.Column('title', sa.String(length=150), nullable=False),
    sa.Column('decision_payload_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True),
    sa.Column('decision_note', sa.Text(), nullable=True),
    sa.Column('remind_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('reminded_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['assignee_id'], ['users.id'], name=op.f('fk_approval_tasks_assignee_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['automation_id'], ['automations.id'], name=op.f('fk_approval_tasks_automation_id_automations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['decided_by'], ['users.id'], name=op.f('fk_approval_tasks_decided_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['run_id'], ['runs.id'], name=op.f('fk_approval_tasks_run_id_runs'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['step_run_id'], ['step_runs.id'], name=op.f('fk_approval_tasks_step_run_id_step_runs'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name=op.f('fk_approval_tasks_workspace_id_workspaces'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_approval_tasks'))
    )
    op.create_index(op.f('ix_approval_tasks_run_id'), 'approval_tasks', ['run_id'], unique=False)
    op.create_index(op.f('ix_approval_tasks_step_run_id'), 'approval_tasks', ['step_run_id'], unique=False)
    op.create_index('ix_approval_tasks_workspace_status', 'approval_tasks', ['workspace_id', 'status'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('automations') as batch:
        batch.drop_constraint(op.f('fk_automations_current_version_id_automation_versions'), type_='foreignkey')
    op.drop_index('ix_approval_tasks_workspace_status', table_name='approval_tasks')
    op.drop_index(op.f('ix_approval_tasks_step_run_id'), table_name='approval_tasks')
    op.drop_index(op.f('ix_approval_tasks_run_id'), table_name='approval_tasks')
    op.drop_table('approval_tasks')
    op.drop_index(op.f('ix_step_runs_run_id'), table_name='step_runs')
    op.drop_table('step_runs')
    op.drop_index(op.f('ix_runs_workspace_id'), table_name='runs')
    op.drop_index('ix_runs_workspace_created', table_name='runs')
    op.drop_index(op.f('ix_runs_automation_id'), table_name='runs')
    op.drop_table('runs')
    op.drop_index(op.f('ix_automation_versions_automation_id'), table_name='automation_versions')
    op.drop_table('automation_versions')
    op.drop_index(op.f('ix_automations_workspace_id'), table_name='automations')
    op.drop_index(op.f('ix_automations_trigger_type'), table_name='automations')
    op.drop_table('automations')
    op.drop_index(op.f('ix_opportunities_map_id'), table_name='opportunities')
    op.drop_table('opportunities')
    op.drop_index(op.f('ix_process_steps_map_id'), table_name='process_steps')
    op.drop_table('process_steps')
    op.drop_index(op.f('ix_sandbox_records_connection_id'), table_name='sandbox_records')
    op.drop_table('sandbox_records')
    op.drop_index(op.f('ix_process_maps_workspace_id'), table_name='process_maps')
    op.drop_index(op.f('ix_process_maps_session_id'), table_name='process_maps')
    op.drop_table('process_maps')
    op.drop_index(op.f('ix_interview_messages_session_id'), table_name='interview_messages')
    op.drop_table('interview_messages')
    op.drop_index(op.f('ix_user_tokens_user_id'), table_name='user_tokens')
    op.drop_table('user_tokens')
    op.drop_index(op.f('ix_push_subscriptions_user_id'), table_name='push_subscriptions')
    op.drop_table('push_subscriptions')
    op.drop_index('ix_notifications_user_created', table_name='notifications')
    op.drop_table('notifications')
    op.drop_index(op.f('ix_memberships_workspace_id'), table_name='memberships')
    op.drop_index(op.f('ix_memberships_user_id'), table_name='memberships')
    op.drop_table('memberships')
    op.drop_index('ix_llm_usage_workspace_created', table_name='llm_usage')
    op.drop_table('llm_usage')
    op.drop_index(op.f('ix_invitations_workspace_id'), table_name='invitations')
    op.drop_table('invitations')
    op.drop_index(op.f('ix_interview_sessions_workspace_id'), table_name='interview_sessions')
    op.drop_table('interview_sessions')
    op.drop_index(op.f('ix_connections_workspace_id'), table_name='connections')
    op.drop_index(op.f('ix_connections_external_account_id'), table_name='connections')
    op.drop_table('connections')
    op.drop_index('ix_audit_logs_workspace_created', table_name='audit_logs')
    op.drop_table('audit_logs')
    op.drop_table('workspaces')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
    op.drop_index('uq_templates_active_code', table_name='templates', postgresql_where=sa.text('is_active'), sqlite_where=sa.text('is_active = 1'))
    op.drop_index(op.f('ix_templates_code'), table_name='templates')
    op.drop_table('templates')
    op.drop_index(op.f('ix_email_messages_to_address'), table_name='email_messages')
    op.drop_table('email_messages')
    for enum_name in (
        "approval_kind",
        "approval_status",
        "automation_status",
        "connection_mode",
        "connection_provider",
        "connection_status",
        "interview_status",
        "membership_role",
        "membership_status",
        "message_sender",
        "opportunity_status",
        "run_status",
        "step_run_status",
        "step_type",
        "token_purpose",
        "workspace_status",
    ):
        sa.Enum(name=enum_name).drop(op.get_bind(), checkfirst=True)
