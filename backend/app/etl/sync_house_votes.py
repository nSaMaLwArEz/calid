import argparse
import asyncio

from app.config import get_settings
from app.congress_client import CongressClient
from app.database import SessionLocal, engine
from app.models import Base
from app.vote_sync import sync_house_votes


async def run(congress: int, session: int, limit: int, offset: int) -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        response = await sync_house_votes(
            db=db,
            congress_client=CongressClient(get_settings()),
            congress=congress,
            session=session,
            limit=limit,
            offset=offset,
        )
        print(response.model_dump_json(indent=2))
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync House roll-call vote rosters into the CALID database.")
    parser.add_argument("--congress", type=int, default=119)
    parser.add_argument("--session", type=int, default=1)
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--offset", type=int, default=0)
    args = parser.parse_args()
    asyncio.run(run(congress=args.congress, session=args.session, limit=args.limit, offset=args.offset))


if __name__ == "__main__":
    main()
