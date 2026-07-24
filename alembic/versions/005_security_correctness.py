"""session security and correctness

Revision ID: 005_security_correctness
Revises: 004_production_operations
Create Date: 2026-07-23
"""
from alembic import op
import sqlalchemy as sa


revision = "005_security_correctness"
down_revision = "004_production_operations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("sessions", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("sessions", sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE sessions SET last_seen_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP)")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("UPDATE sessions SET expires_at = COALESCE(created_at, CURRENT_TIMESTAMP) + INTERVAL '168 hours'")
    else:
        op.execute("UPDATE sessions SET expires_at = datetime(COALESCE(created_at, CURRENT_TIMESTAMP), '+168 hours')")
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("sessions") as batch_op:
            batch_op.alter_column("expires_at", existing_type=sa.DateTime(timezone=True), nullable=False)
            batch_op.alter_column("last_seen_at", existing_type=sa.DateTime(timezone=True), nullable=False)
    else:
        op.alter_column("sessions", "expires_at", nullable=False)
        op.alter_column("sessions", "last_seen_at", nullable=False)


def downgrade() -> None:
    op.drop_column("sessions", "revoked_at")
    op.drop_column("sessions", "last_seen_at")
    op.drop_column("sessions", "expires_at")
