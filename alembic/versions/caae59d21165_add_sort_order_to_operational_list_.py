"""add sort_order to operational list tables

Revision ID: caae59d21165
Revises: 1740ccf419d5
Create Date: 2026-06-20 15:10:57.867943

PostgreSQL does not guarantee row order the way the existing clients.json
list fields (opportunities, target_contacts, session_notes, action_items)
preserve insertion order. This adds a non-null `sort_order` integer column
to each of those four tables so the storage adapter can reconstruct the
exact original list order, and replaces each table's plain client_id index
with a composite (client_id, sort_order) index that also serves ordered
per-client lookups.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'caae59d21165'
down_revision: Union[str, None] = '1740ccf419d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ["opportunities", "target_contacts", "session_notes", "action_items"]


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(
            table,
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        )
        op.drop_index(f"ix_{table}_client_id", table_name=table)
        op.create_index(
            f"ix_{table}_client_id_sort_order", table, ["client_id", "sort_order"]
        )


def downgrade() -> None:
    for table in _TABLES:
        op.drop_index(f"ix_{table}_client_id_sort_order", table_name=table)
        op.create_index(f"ix_{table}_client_id", table, ["client_id"])
        op.drop_column(table, "sort_order")
