"""pipeline schema: transcripts, chunks, note embeddings, alignments

Revision ID: 0002
Revises: 0001
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision = "0002"
down_revision = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("notes", sa.Column("embedding", sa.ARRAY(sa.Float()), nullable=True))

    op.create_table(
        "transcripts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("lecture_id", sa.UUID(), nullable=False),
        sa.Column("full_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["lecture_id"], ["lectures.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_transcripts_lecture_id"), "transcripts", ["lecture_id"], unique=True)

    op.create_table(
        "transcript_chunks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("transcript_id", sa.UUID(), nullable=False),
        sa.Column("chunk_index", sa.BigInteger(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("start_ms", sa.BigInteger(), nullable=False),
        sa.Column("end_ms", sa.BigInteger(), nullable=False),
        sa.Column("embedding", sa.ARRAY(sa.Float()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["transcript_id"], ["transcripts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_transcript_chunks_transcript_id"), "transcript_chunks", ["transcript_id"], unique=False
    )

    op.create_table(
        "note_alignments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("note_id", sa.UUID(), nullable=False),
        sa.Column("transcript_chunk_id", sa.UUID(), nullable=False),
        sa.Column("similarity", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["note_id"], ["notes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["transcript_chunk_id"], ["transcript_chunks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_note_alignments_note_id"), "note_alignments", ["note_id"], unique=True)
    op.create_index(
        op.f("ix_note_alignments_transcript_chunk_id"), "note_alignments", ["transcript_chunk_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_note_alignments_transcript_chunk_id"), table_name="note_alignments")
    op.drop_index(op.f("ix_note_alignments_note_id"), table_name="note_alignments")
    op.drop_table("note_alignments")
    op.drop_index(op.f("ix_transcript_chunks_transcript_id"), table_name="transcript_chunks")
    op.drop_table("transcript_chunks")
    op.drop_index(op.f("ix_transcripts_lecture_id"), table_name="transcripts")
    op.drop_table("transcripts")
    op.drop_column("notes", "embedding")
