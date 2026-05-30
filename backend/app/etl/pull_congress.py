import argparse
import asyncio

from app.config import get_settings
from app.congress_client import CongressClient


async def run(congress: int, limit: int) -> None:
    settings = get_settings()
    client = CongressClient(settings)
    if not client.enabled:
        raise SystemExit("CONGRESS_API_KEY is required for live ETL pulls.")

    members = await client.search_members(query=None, state=None, party=None, chamber=None, limit=limit)
    votes = await client.house_votes(congress=congress, session=1, limit=min(limit, 100))
    print(f"Fetched {len(members)} members and {len(votes)} House votes for Congress {congress}.")
    print("Persistence is intentionally stubbed; wire these payloads into SQLAlchemy sessions next.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Pull Congress.gov data for CALID.")
    parser.add_argument("--congress", type=int, default=119)
    parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args()
    asyncio.run(run(congress=args.congress, limit=args.limit))


if __name__ == "__main__":
    main()
