"""add payment_orders table

Revision ID: a1b2c3d4e5f6
Revises: f675ecae4205
Create Date: 2026-03-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f675ecae4205'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'payment_orders',
        sa.Column('id',              sa.Integer(),     primary_key=True),
        sa.Column('user_id',         sa.Integer(),     sa.ForeignKey('users.id',     ondelete='SET NULL'), nullable=True),
        sa.Column('campaign_id',     sa.Integer(),     sa.ForeignKey('campaigns.id', ondelete='CASCADE'), nullable=False),
        sa.Column('milestone_id',    sa.Integer(),     sa.ForeignKey('milestones.id',ondelete='CASCADE'), nullable=False),
        sa.Column('donation_id',     sa.Integer(),     sa.ForeignKey('donations.id', ondelete='SET NULL'), nullable=True),
        sa.Column('amount',          sa.Float(),       nullable=False),
        sa.Column('is_anonymous',    sa.Boolean(),     nullable=False, server_default=sa.text('false')),
        sa.Column('anonymous_email', sa.Text(),        nullable=True),
        sa.Column('order_id',        sa.String(64),    nullable=False, unique=True),
        sa.Column('payment_id',      sa.String(64),    nullable=True),
        sa.Column('gateway',         sa.String(32),    nullable=False, server_default=sa.text("'mock'")),
        sa.Column('status',          sa.String(16),    nullable=False, server_default=sa.text("'pending'")),
        sa.Column('expires_at',      sa.DateTime(),    nullable=False),
        sa.Column('created_at',      sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at',      sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_payment_orders_order_id', 'payment_orders', ['order_id'], unique=True)
    op.create_index('ix_payment_orders_id',       'payment_orders', ['id'],       unique=False)


def downgrade() -> None:
    op.drop_index('ix_payment_orders_order_id', table_name='payment_orders')
    op.drop_index('ix_payment_orders_id',       table_name='payment_orders')
    op.drop_table('payment_orders')
