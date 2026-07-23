"""production operations

Revision ID: 004_production_operations
Revises: 003_scheduler_queue
Create Date: 2026-07-22
"""
from alembic import op
import sqlalchemy as sa

revision = "004_production_operations"
down_revision = "003_scheduler_queue"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("execution_queue_items", sa.Column("claimed_by", sa.String(255)))
    op.add_column("worker_heartbeats", sa.Column("last_error", sa.Text()))


def downgrade() -> None:
    op.drop_column("worker_heartbeats", "last_error")
    op.drop_column("execution_queue_items", "claimed_by")
    op.drop_column("users", "must_change_password")
