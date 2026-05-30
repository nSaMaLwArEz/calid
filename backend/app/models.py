from sqlalchemy import Boolean, Date, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Member(Base):
    __tablename__ = "members"

    bioguide_id: Mapped[str] = mapped_column(String(12), primary_key=True)
    name: Mapped[str] = mapped_column(String(240), index=True)
    state: Mapped[str] = mapped_column(String(2), index=True)
    party: Mapped[str] = mapped_column(String(32), index=True)
    chamber: Mapped[str] = mapped_column(String(16), index=True)
    district: Mapped[str | None] = mapped_column(String(8), nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    sponsored_bills: Mapped[list["Bill"]] = relationship(back_populates="sponsor")


class Bill(Base):
    __tablename__ = "bills"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    congress: Mapped[int] = mapped_column(Integer, index=True)
    bill_type: Mapped[str] = mapped_column(String(12), index=True)
    number: Mapped[str] = mapped_column(String(24), index=True)
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    latest_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    latest_action_date: Mapped[str | None] = mapped_column(String(24), nullable=True)
    policy_area: Mapped[str | None] = mapped_column(String(120), nullable=True)
    sponsor_bioguide_id: Mapped[str | None] = mapped_column(ForeignKey("members.bioguide_id"), nullable=True)

    sponsor: Mapped[Member | None] = relationship(back_populates="sponsored_bills")


class CommitteeAssignment(Base):
    __tablename__ = "committee_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    member_bioguide_id: Mapped[str] = mapped_column(ForeignKey("members.bioguide_id"), index=True)
    chamber: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(240))
    rank: Mapped[str | None] = mapped_column(String(120), nullable=True)


class RollCallVote(Base):
    __tablename__ = "roll_call_votes"
    __table_args__ = (UniqueConstraint("congress", "session", "chamber", "roll_call_number", name="uq_roll_call_vote"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    congress: Mapped[int] = mapped_column(Integer, index=True)
    session: Mapped[int] = mapped_column(Integer, index=True)
    chamber: Mapped[str] = mapped_column(String(16), index=True)
    roll_call_number: Mapped[int] = mapped_column(Integer, index=True)
    question: Mapped[str] = mapped_column(Text)
    result: Mapped[str | None] = mapped_column(String(120), nullable=True)
    date: Mapped[Date | None] = mapped_column(Date, nullable=True)
    bill_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    positions: Mapped[list["VotePosition"]] = relationship(back_populates="vote_record", cascade="all, delete-orphan")


class VotePosition(Base):
    __tablename__ = "vote_positions"
    __table_args__ = (UniqueConstraint("roll_call_vote_id", "member_bioguide_id", name="uq_vote_position_member"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    roll_call_vote_id: Mapped[int] = mapped_column(ForeignKey("roll_call_votes.id"), index=True)
    member_bioguide_id: Mapped[str] = mapped_column(String(12), index=True)
    member_name: Mapped[str] = mapped_column(String(240), index=True)
    state: Mapped[str | None] = mapped_column(String(2), nullable=True, index=True)
    party: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    vote: Mapped[str] = mapped_column(String(40), index=True)

    vote_record: Mapped[RollCallVote] = relationship(back_populates="positions")
