from sqlalchemy.orm import Session

from app.congress_client import CongressClient
from app.schemas import VoteSyncResponse
from app.vote_cache import upsert_vote_with_positions


async def sync_house_votes(
    db: Session,
    congress_client: CongressClient,
    congress: int,
    session: int,
    limit: int,
    offset: int,
) -> VoteSyncResponse:
    if not congress_client.enabled:
        raise RuntimeError("CONGRESS_API_KEY is required to sync live House vote data.")

    votes, total = await congress_client.house_vote_page(congress=congress, session=session, limit=limit, offset=offset)
    stored_votes = 0
    stored_positions = 0
    for vote in votes:
        detailed_vote, members = await congress_client.house_vote_members(congress, session, vote.roll_call_number)
        vote_count, position_count = upsert_vote_with_positions(db, detailed_vote, members)
        stored_votes += vote_count
        stored_positions += position_count

    db.commit()
    return VoteSyncResponse(
        congress=congress,
        session=session,
        scanned_votes=len(votes),
        stored_votes=stored_votes,
        stored_positions=stored_positions,
        offset=offset,
        limit=limit,
        total_available=total,
        note="Synced House roll-call votes and member positions into the local database.",
    )
