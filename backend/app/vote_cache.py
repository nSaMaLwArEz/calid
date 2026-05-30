from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from app.models import RollCallVote, VotePosition
from app.schemas import MemberSummary, MemberVotingProfile, MonthlyVoteSummary, Vote, VoteBillSummary, VoteMember


NOT_PARTICIPATING = {"not voting", "not-voting", "absent", "missing"}


def has_cached_votes(db: Session, congress: int, session: int) -> bool:
    return (
        db.scalar(
            select(func.count(RollCallVote.id)).where(
                RollCallVote.congress == congress,
                RollCallVote.session == session,
                RollCallVote.chamber == "House",
            )
        )
        or 0
    ) > 0


def upsert_vote_with_positions(db: Session, vote: VoteBillSummary | Vote, members: list[VoteMember]) -> tuple[int, int]:
    vote_record = db.scalar(
        select(RollCallVote).where(
            RollCallVote.congress == vote.congress,
            RollCallVote.session == vote.session,
            RollCallVote.chamber == vote.chamber,
            RollCallVote.roll_call_number == vote.roll_call_number,
        )
    )
    if vote_record is None:
        vote_record = RollCallVote(
            congress=vote.congress,
            session=vote.session,
            chamber=vote.chamber,
            roll_call_number=vote.roll_call_number,
            question=vote.question,
        )
        db.add(vote_record)
        db.flush()

    vote_record.question = vote.question
    vote_record.result = vote.result
    vote_record.date = _parse_date(vote.date)
    vote_record.bill_id = vote.bill_id
    vote_record.source_url = vote.source_url

    stored_positions = 0
    for member in members:
        if not member.bioguide_id:
            continue
        position = db.scalar(
            select(VotePosition).where(
                VotePosition.roll_call_vote_id == vote_record.id,
                VotePosition.member_bioguide_id == member.bioguide_id,
            )
        )
        if position is None:
            position = VotePosition(roll_call_vote_id=vote_record.id, member_bioguide_id=member.bioguide_id, member_name=member.name, vote=member.vote)
            db.add(position)

        position.member_name = member.name
        position.state = member.state
        position.party = member.party
        position.vote = member.vote
        stored_positions += 1

    return 1, stored_positions


def cached_vote_bills(db: Session, congress: int, session: int, limit: int, offset: int) -> tuple[list[VoteBillSummary], int]:
    total = db.scalar(_roll_call_base(congress, session).with_only_columns(func.count()).order_by(None)) or 0
    votes = db.scalars(
        _roll_call_base(congress, session)
        .options(selectinload(RollCallVote.positions))
        .order_by(RollCallVote.date.desc().nullslast(), RollCallVote.roll_call_number.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return [_vote_bill_summary(vote) for vote in votes], total


def cached_vote_members(db: Session, congress: int, session: int, roll_call_number: int) -> tuple[VoteBillSummary | None, list[VoteMember]]:
    vote = db.scalar(
        _roll_call_base(congress, session)
        .where(RollCallVote.roll_call_number == roll_call_number)
        .options(selectinload(RollCallVote.positions))
    )
    if vote is None:
        return None, []
    return _vote_bill_summary(vote), [_vote_member(position) for position in sorted(vote.positions, key=lambda item: item.member_name)]


def cached_member_voting_profile(
    db: Session,
    member: MemberSummary,
    congress: int,
    session: int,
) -> MemberVotingProfile | None:
    roll_calls = db.scalars(
        _roll_call_base(congress, session)
        .options(selectinload(RollCallVote.positions))
        .order_by(RollCallVote.date.asc().nullsfirst(), RollCallVote.roll_call_number.asc())
    ).all()
    if not roll_calls:
        return None

    member_votes: list[Vote] = []
    for roll_call in roll_calls:
        position = next((item for item in roll_call.positions if item.member_bioguide_id == member.bioguide_id), None)
        if position:
            member_votes.append(_vote(roll_call, position.vote))

    participated = len([vote for vote in member_votes if _participated(vote.member_position)])
    return MemberVotingProfile(
        member=member,
        votes=member_votes,
        monthly=_monthly_summary(roll_calls, member_votes),
        total_votes=len(roll_calls),
        scanned_votes=len(roll_calls),
        available_votes=len(roll_calls),
        participated=participated,
        missed=max(len(roll_calls) - participated, 0),
        note="Voting history is computed from cached House roll-call vote rosters in the database.",
    )


def _roll_call_base(congress: int, session: int) -> Select[tuple[RollCallVote]]:
    return select(RollCallVote).where(
        RollCallVote.congress == congress,
        RollCallVote.session == session,
        RollCallVote.chamber == "House",
    )


def _vote_bill_summary(vote: RollCallVote) -> VoteBillSummary:
    counts = Counter(_bucket(position.vote) for position in vote.positions)
    return VoteBillSummary(
        **_vote(vote).model_dump(),
        yea=counts["yea"],
        nay=counts["nay"],
        abstained=counts["abstained"],
        not_voting=counts["not_voting"],
    )


def _vote(vote: RollCallVote, member_position: str | None = None) -> Vote:
    return Vote(
        congress=vote.congress,
        session=vote.session,
        chamber=vote.chamber,
        roll_call_number=vote.roll_call_number,
        date=vote.date.isoformat() if vote.date else None,
        question=vote.question,
        result=vote.result,
        bill_id=vote.bill_id,
        member_position=member_position,
        source_url=vote.source_url,
    )


def _vote_member(position: VotePosition) -> VoteMember:
    return VoteMember(
        bioguide_id=position.member_bioguide_id,
        name=position.member_name,
        state=position.state,
        party=position.party,
        vote=position.vote,
    )


def _monthly_summary(roll_calls: list[RollCallVote], member_votes: list[Vote]) -> list[MonthlyVoteSummary]:
    total_by_month: dict[str, int] = defaultdict(int)
    participated_by_month: dict[str, int] = defaultdict(int)
    for roll_call in roll_calls:
        if roll_call.date:
            total_by_month[roll_call.date.strftime("%Y-%m")] += 1

    for vote in member_votes:
        if vote.date and _participated(vote.member_position):
            participated_by_month[vote.date[:7]] += 1

    return [
        MonthlyVoteSummary(
            month=month,
            participated=participated_by_month.get(month, 0),
            total=total,
            missed=max(total - participated_by_month.get(month, 0), 0),
        )
        for month, total in sorted(total_by_month.items())
    ]


def _bucket(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    if normalized in {"yea", "aye", "yes"}:
        return "yea"
    if normalized in {"nay", "no"}:
        return "nay"
    if normalized in {"present", "abstain", "abstained"}:
        return "abstained"
    return "not_voting"


def _participated(position: str | None) -> bool:
    return bool(position) and position.strip().lower() not in NOT_PARTICIPATING


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).date()
    except ValueError:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
