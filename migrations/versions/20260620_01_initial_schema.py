"""Initial versioned schema, preserving existing legacy tables."""

from alembic import op
import sqlalchemy as sa

revision = "20260620_01"
down_revision = None
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    tables = _tables()
    if "device_info" not in tables:
        op.create_table(
            "device_info",
            sa.Column("device_id", sa.String(50), primary_key=True),
            sa.Column("station_name", sa.String(100), nullable=False),
            sa.Column("location", sa.String(100)),
        )
        op.create_index("ix_device_info_device_id", "device_info", ["device_id"])
    if "ai_label_map" not in tables:
        op.create_table(
            "ai_label_map",
            sa.Column("label_id", sa.Integer(), primary_key=True),
            sa.Column("word_name", sa.String(10), nullable=False),
            sa.Column("description", sa.String(255)),
        )
        op.create_index("ix_ai_label_map_label_id", "ai_label_map", ["label_id"])
    if "communication_log" not in tables:
        op.create_table(
            "communication_log",
            sa.Column("log_id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("device_id", sa.String(50), sa.ForeignKey("device_info.device_id"), nullable=False),
            sa.Column("label_id", sa.Integer(), sa.ForeignKey("ai_label_map.label_id"), nullable=False),
            sa.Column("recognized_word", sa.String(50), nullable=False),
            sa.Column("staff_reply", sa.Text()),
            sa.Column("status", sa.String(9), nullable=False, server_default="WAITING"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_communication_log_log_id", "communication_log", ["log_id"])
        op.create_index("ix_communication_log_device_id", "communication_log", ["device_id"])
        op.create_index("ix_communication_log_label_id", "communication_log", ["label_id"])
        op.create_index("ix_communication_log_status", "communication_log", ["status"])
        op.create_index("ix_communication_log_created_at", "communication_log", ["created_at"])
        op.create_index("ix_comm_log_device_status", "communication_log", ["device_id", "status"])
    if "training_data_log" not in tables:
        op.create_table(
            "training_data_log",
            sa.Column("data_id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("log_id", sa.Integer(), sa.ForeignKey("communication_log.log_id"), nullable=False, unique=True),
            sa.Column("raw_json_data", sa.JSON(), nullable=False),
        )
        op.create_index("ix_training_data_log_data_id", "training_data_log", ["data_id"])
    if "conversation" not in tables:
        op.create_table(
            "conversation",
            sa.Column("conversation_id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("device_id", sa.String(50), sa.ForeignKey("device_info.device_id"), nullable=False),
            sa.Column("question_text", sa.Text(), nullable=False),
            sa.Column("staff_reply", sa.Text()),
            sa.Column("status", sa.String(9), nullable=False, server_default="WAITING"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_conversation_conversation_id", "conversation", ["conversation_id"])
        op.create_index("ix_conversation_device_id", "conversation", ["device_id"])
        op.create_index("ix_conversation_status", "conversation", ["status"])
        op.create_index("ix_conversation_created_at", "conversation", ["created_at"])
        op.create_index("ix_conversation_device_status", "conversation", ["device_id", "status"])


def downgrade() -> None:
    for table in ["conversation", "training_data_log", "communication_log", "ai_label_map", "device_info"]:
        if table in _tables():
            op.drop_table(table)
