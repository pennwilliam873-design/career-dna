"""extend target_contacts for Hidden Market Map

Revision ID: 7d2f9a4c1b6e
Revises: caae59d21165
Create Date: 2026-06-21 09:00:00.000000

Purely additive: every new column is nullable=False with a server_default,
so existing rows (and any in-flight inserts during deploy) get a safe value
with no application code change required at the database level.

Also backfills `status` on existing rows from the pre-Hidden-Market-Map
vocabulary ("Not contacted", "Warm path identified", "Responded", ...) to
the new vocabulary ("To assess", "Ready for outreach", "Active
conversation", ...). `status` stays a free-text column (not a DB-level
enum) — any value outside the mapped set (including values the advisor
later picks from the new UI) passes through untouched, matching how
`status` already behaves on opportunities and action_items.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '7d2f9a4c1b6e'
down_revision: Union[str, None] = 'caae59d21165'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_NEW_TEXT_COLUMNS = [
    ("network_source", "Unknown"),
    ("relationship_owner", "Unknown"),
    ("relationship_to_client", ""),
    ("relationship_to_advisor", ""),
    ("relationship_strength", "Unknown"),
    ("last_contacted_at", ""),
    ("role_in_search", "Unknown"),
    ("target_company", ""),
    ("target_sector", ""),
    ("linked_market_radar_company", ""),
    ("linked_market_radar_tier", ""),
    ("linked_opportunity_id", ""),
    ("linked_opportunity_title", ""),
    ("relevance_rationale", ""),
    ("opportunity_path_hypothesis", ""),
    ("can_make_intro", "unknown"),
    ("bridge_to", ""),
    ("warm_path_status", "Unknown"),
    ("ask_type", "Unknown"),
    ("suggested_approach", ""),
    ("next_action", ""),
    ("next_action_owner", "Advisor"),
    ("next_action_due_date", ""),
    ("follow_up_date", ""),
    ("outreach_channel", ""),
    ("response_notes", ""),
    ("advisor_notes", ""),
]

_NEW_BOOLEAN_COLUMNS = [
    ("advisor_only", True),
    ("client_shareable", False),
    ("approved_for_outreach", False),
    ("sensitive", False),
    ("do_not_contact_yet", False),
    ("include_in_advisor_brief", False),
    ("include_in_weekly_plan", False),
]

# Pre-Hidden-Market-Map status -> new status vocabulary.
_STATUS_MAP = {
    "Not contacted": "To assess",
    "Warm path identified": "Ready for outreach",
    "Responded": "Active conversation",
}


def upgrade() -> None:
    for name, default in _NEW_TEXT_COLUMNS:
        op.add_column(
            "target_contacts",
            sa.Column(name, sa.Text(), nullable=False, server_default=default),
        )
    for name, default in _NEW_BOOLEAN_COLUMNS:
        op.add_column(
            "target_contacts",
            sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.true() if default else sa.false()),
        )

    op.alter_column(
        "target_contacts", "status",
        server_default="To assess",
    )

    for old_value, new_value in _STATUS_MAP.items():
        op.execute(
            sa.text(
                "UPDATE target_contacts SET status = :new_value WHERE status = :old_value"
            ).bindparams(new_value=new_value, old_value=old_value)
        )


def downgrade() -> None:
    op.alter_column(
        "target_contacts", "status",
        server_default="Not contacted",
    )
    _reverse_status_map = {v: k for k, v in _STATUS_MAP.items()}
    for new_value, old_value in _reverse_status_map.items():
        op.execute(
            sa.text(
                "UPDATE target_contacts SET status = :old_value WHERE status = :new_value"
            ).bindparams(old_value=old_value, new_value=new_value)
        )

    for name, _ in _NEW_BOOLEAN_COLUMNS:
        op.drop_column("target_contacts", name)
    for name, _ in _NEW_TEXT_COLUMNS:
        op.drop_column("target_contacts", name)
