"""initial schema

Revision ID: 0001
Revises: 
Create Date: 2026-10-20 12:10:39.520216
"""
from alembic import op
import sqlalchemy as sa


revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('emotions',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('quadrant', sa.String(length=10), nullable=False),
    sa.Column('energy', sa.Integer(), nullable=False),
    sa.Column('pleasantness', sa.Integer(), nullable=False),
    sa.Column('intensity', sa.Integer(), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('hidden', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('login_attempts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('key_hash', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('login_attempts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_login_attempts_key_hash'), ['key_hash'], unique=False)

    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('is_admin', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email')
    )
    op.create_table('checkins',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('emotion_id', sa.String(length=64), nullable=False),
    sa.Column('occurred_at', sa.DateTime(), nullable=False),
    sa.Column('local_date', sa.Date(), nullable=False),
    sa.Column('source', sa.String(length=20), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint("source IN ('manual','evening','notification')", name='ck_checkins_source'),
    sa.ForeignKeyConstraint(['emotion_id'], ['emotions.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('checkins', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_checkins_local_date'), ['local_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_checkins_user_id'), ['user_id'], unique=False)

    op.create_table('day_logs',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('local_date', sa.Date(), nullable=False),
    sa.Column('plan_status', sa.String(length=3), nullable=True),
    sa.Column('plan_text', sa.Text(), nullable=True),
    sa.Column('sleep_hours', sa.Float(), nullable=True),
    sa.Column('sleep_quality', sa.Integer(), nullable=True),
    sa.Column('sport_type', sa.String(length=100), nullable=True),
    sa.Column('sport_minutes', sa.Integer(), nullable=True),
    sa.Column('day_summary', sa.Text(), nullable=True),
    sa.Column('plan_remind_at', sa.DateTime(), nullable=True),
    sa.CheckConstraint("plan_status IS NULL OR plan_status IN ('yes','no')", name='ck_day_logs_plan'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'local_date')
    )
    op.create_table('notification_log',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=30), nullable=False),
    sa.Column('local_date', sa.Date(), nullable=False),
    sa.Column('sent_at', sa.DateTime(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'kind', 'local_date', name='uq_notification_log')
    )
    op.create_table('push_subscriptions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('endpoint', sa.Text(), nullable=False),
    sa.Column('p256dh', sa.String(length=255), nullable=False),
    sa.Column('auth', sa.String(length=255), nullable=False),
    sa.Column('user_agent', sa.String(length=500), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('last_ok_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('endpoint')
    )
    with op.batch_alter_table('push_subscriptions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_push_subscriptions_user_id'), ['user_id'], unique=False)

    op.create_table('sessions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('user_agent', sa.String(length=500), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash')
    )
    with op.batch_alter_table('sessions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_sessions_user_id'), ['user_id'], unique=False)

    op.create_table('settings',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('timezone', sa.String(length=64), nullable=False),
    sa.Column('morning_enabled', sa.Boolean(), nullable=False),
    sa.Column('morning_time', sa.String(length=5), nullable=False),
    sa.Column('morning_text', sa.Text(), nullable=False),
    sa.Column('evening_enabled', sa.Boolean(), nullable=False),
    sa.Column('evening_time', sa.String(length=5), nullable=False),
    sa.Column('evening_text', sa.Text(), nullable=False),
    sa.Column('repeat_enabled', sa.Boolean(), nullable=False),
    sa.Column('repeat_after_min', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id')
    )
    op.create_table('tags',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('group', sa.String(length=10), nullable=False),
    sa.Column('name', sa.String(length=60), nullable=False),
    sa.Column('sort', sa.Integer(), nullable=False),
    sa.Column('hidden', sa.Boolean(), nullable=False),
    sa.CheckConstraint('"group" IN (\'with\',\'where\',\'doing\')', name='ck_tags_group'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('tags', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_tags_user_id'), ['user_id'], unique=False)

    op.create_table('checkin_tags',
    sa.Column('checkin_id', sa.Integer(), nullable=False),
    sa.Column('tag_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['checkin_id'], ['checkins.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tag_id'], ['tags.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('checkin_id', 'tag_id')
    )
    op.create_table('media',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('checkin_id', sa.Integer(), nullable=True),
    sa.Column('day_log_date', sa.Date(), nullable=True),
    sa.Column('kind', sa.String(length=10), nullable=False),
    sa.Column('path', sa.String(length=500), nullable=False),
    sa.Column('mime', sa.String(length=100), nullable=False),
    sa.Column('size', sa.Integer(), nullable=False),
    sa.Column('duration_s', sa.Float(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint("kind IN ('photo','audio')", name='ck_media_kind'),
    sa.CheckConstraint('(checkin_id IS NULL) <> (day_log_date IS NULL)', name='ck_media_one_link'),
    sa.ForeignKeyConstraint(['checkin_id'], ['checkins.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('media', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_media_user_id'), ['user_id'], unique=False)



def downgrade() -> None:
    with op.batch_alter_table('media', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_media_user_id'))

    op.drop_table('media')
    op.drop_table('checkin_tags')
    with op.batch_alter_table('tags', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_tags_user_id'))

    op.drop_table('tags')
    op.drop_table('settings')
    with op.batch_alter_table('sessions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_sessions_user_id'))

    op.drop_table('sessions')
    with op.batch_alter_table('push_subscriptions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_push_subscriptions_user_id'))

    op.drop_table('push_subscriptions')
    op.drop_table('notification_log')
    op.drop_table('day_logs')
    with op.batch_alter_table('checkins', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_checkins_user_id'))
        batch_op.drop_index(batch_op.f('ix_checkins_local_date'))

    op.drop_table('checkins')
    op.drop_table('users')
    with op.batch_alter_table('login_attempts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_login_attempts_key_hash'))

    op.drop_table('login_attempts')
    op.drop_table('emotions')
