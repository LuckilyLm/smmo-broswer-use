"""remaining production hardening

Revision ID: 006_prod_hardening
Revises: 005_security_correctness
Create Date: 2026-07-23
"""
from alembic import op
import sqlalchemy as sa


revision = "006_prod_hardening"
down_revision = "005_security_correctness"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("campaigns", sa.Column("deleted_at", sa.DateTime(timezone=True)))
    op.add_column("leads", sa.Column("final_intent_level", sa.String(length=50)))
    op.add_column("executions", sa.Column("cancel_requested_at", sa.DateTime(timezone=True)))
    op.add_column("executions", sa.Column("config_snapshot", sa.JSON(), nullable=True))
    op.execute("UPDATE executions SET config_snapshot = '{}' WHERE config_snapshot IS NULL")
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("executions") as batch_op:
            batch_op.alter_column("config_snapshot", existing_type=sa.JSON(), nullable=False)
    else:
        op.alter_column("executions", "config_snapshot", nullable=False)
    op.add_column("execution_queue_items", sa.Column("attempt_token", sa.String(length=64)))
    op.add_column("execution_keywords", sa.Column("attempt_number", sa.Integer(), nullable=True))
    op.execute("UPDATE execution_keywords SET attempt_number = 1 WHERE attempt_number IS NULL")
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("execution_keywords") as batch_op:
            batch_op.alter_column("attempt_number", existing_type=sa.Integer(), nullable=False)
            batch_op.create_unique_constraint(
                "uq_execution_keywords_execution_keyword",
                ["execution_id", "keyword"],
            )
    else:
        op.alter_column("execution_keywords", "attempt_number", nullable=False)
        op.create_unique_constraint(
            "uq_execution_keywords_execution_keyword",
            "execution_keywords",
            ["execution_id", "keyword"],
        )
    op.add_column("token_usage", sa.Column("elapsed_ms", sa.Integer()))
    op.add_column("token_usage", sa.Column("attempt_number", sa.Integer(), nullable=True))
    op.execute("UPDATE token_usage SET attempt_number = 1 WHERE attempt_number IS NULL")
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("token_usage") as batch_op:
            batch_op.alter_column("attempt_number", existing_type=sa.Integer(), nullable=False)
    else:
        op.alter_column("token_usage", "attempt_number", nullable=False)
    op.create_index(
        "uq_token_usage_execution_keyword",
        "token_usage",
        ["execution_keyword_id"],
        unique=True,
        postgresql_where=sa.text("execution_keyword_id IS NOT NULL"),
        sqlite_where=sa.text("execution_keyword_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_token_usage_execution_keyword", table_name="token_usage")
    op.drop_column("token_usage", "attempt_number")
    op.drop_column("token_usage", "elapsed_ms")
    op.drop_constraint("uq_execution_keywords_execution_keyword", "execution_keywords", type_="unique")
    op.drop_column("execution_keywords", "attempt_number")
    op.drop_column("execution_queue_items", "attempt_token")
    op.drop_column("executions", "config_snapshot")
    op.drop_column("executions", "cancel_requested_at")
    op.drop_column("leads", "final_intent_level")
    op.drop_column("campaigns", "deleted_at")
