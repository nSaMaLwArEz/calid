from pathlib import Path
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings
from app.congress_client import CongressClient
from app.repository import LegislativeRepository
from app.schemas import AnalyticsResponse, BillDetail, BillListResponse, HealthResponse, MemberListResponse, MemberProfile, MemberVotingProfile, VoteBillListResponse, VoteExplorerResponse, VoteMemberListResponse


def get_repository(settings: Settings = Depends(get_settings)) -> LegislativeRepository:
    return LegislativeRepository(CongressClient(settings))


app = FastAPI(title="CALID API", version="0.1.0")
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
INDEX_FILE = STATIC_DIR / "index.html"

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    if INDEX_FILE.exists():
        return FileResponse(INDEX_FILE)

    return {
        "name": "CALID API",
        "status": "live",
        "docs": "/docs",
        "health": "/health",
        "endpoints": [
            "/members",
            "/members/{bioguide_id}",
            "/bills",
            "/bills/{bill_id}",
            "/votes/house",
            "/analytics",
        ],
    }


@app.get("/health", response_model=HealthResponse)
async def health(repository: LegislativeRepository = Depends(get_repository)) -> HealthResponse:
    return HealthResponse(status="ok", data_mode=repository.data_mode)


@app.get("/diagnostics/congress")
async def congress_diagnostics(settings: Settings = Depends(get_settings)) -> dict[str, object]:
    diagnostics: dict[str, object] = {
        "api_key_configured": bool(settings.congress_api_key),
        "base_url": str(settings.congress_api_base_url),
    }
    if not settings.congress_api_key:
        diagnostics["status"] = "missing_api_key"
        return diagnostics

    try:
        async with httpx.AsyncClient(base_url=str(settings.congress_api_base_url), timeout=20) as client:
            response = await client.get(
                "member",
                params={"api_key": settings.congress_api_key.strip(), "format": "json", "limit": 1},
            )
            diagnostics["status_code"] = response.status_code
            response.raise_for_status()
            payload = response.json()
            diagnostics["status"] = "ok"
            diagnostics["member_count"] = len(payload.get("members", []))
            diagnostics["total"] = payload.get("pagination", {}).get("count")
            return diagnostics
    except Exception as exc:
        diagnostics["status"] = "error"
        diagnostics["error"] = _redact_api_key(str(exc))
        return diagnostics


def _redact_api_key(message: str) -> str:
    def redact_url(match: re.Match[str]) -> str:
        parts = urlsplit(match.group(0))
        if not parts.query:
            return match.group(0)

        query = urlencode(
            [(key, "REDACTED" if key.lower() == "api_key" else value) for key, value in parse_qsl(parts.query, keep_blank_values=True)]
        )
        return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))

    return re.sub(r"https?://[^\s'\"]+", redact_url, message)


@app.get("/members", response_model=MemberListResponse)
async def search_members(
    query: str | None = None,
    state: str | None = Query(default=None, min_length=2, max_length=2),
    party: str | None = None,
    chamber: str | None = None,
    limit: int = Query(default=50, ge=1, le=250),
    offset: int = Query(default=0, ge=0),
    repository: LegislativeRepository = Depends(get_repository),
) -> MemberListResponse:
    return await repository.search_members(query=query, state=state, party=party, chamber=chamber, limit=limit, offset=offset)


@app.get("/bills", response_model=BillListResponse)
async def bills(
    congress: int | None = Query(default=119, ge=1),
    bill_type: str | None = None,
    limit: int = Query(default=50, ge=1, le=250),
    offset: int = Query(default=0, ge=0),
    repository: LegislativeRepository = Depends(get_repository),
) -> BillListResponse:
    return await repository.bills(congress=congress, bill_type=bill_type, limit=limit, offset=offset)


@app.get("/members/{bioguide_id}", response_model=MemberProfile)
async def member_profile(
    bioguide_id: str,
    repository: LegislativeRepository = Depends(get_repository),
) -> MemberProfile:
    profile = await repository.member_profile(bioguide_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Member not found")
    return profile


@app.get("/members/{bioguide_id}/voting", response_model=MemberVotingProfile)
async def member_voting_profile(
    bioguide_id: str,
    congress: int = Query(default=119, ge=1),
    session: int = Query(default=1, ge=1, le=2),
    limit: int = Query(default=50, ge=1, le=100),
    repository: LegislativeRepository = Depends(get_repository),
) -> MemberVotingProfile:
    profile = await repository.member_voting_profile(bioguide_id=bioguide_id, congress=congress, session=session, limit=limit)
    if not profile:
        raise HTTPException(status_code=404, detail="Member not found")
    return profile


@app.get("/bills/{bill_id}", response_model=BillDetail)
async def bill_detail(
    bill_id: str,
    repository: LegislativeRepository = Depends(get_repository),
) -> BillDetail:
    bill = await repository.bill_detail(bill_id)
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    return bill


@app.get("/vote-bills", response_model=VoteBillListResponse)
async def vote_bills(
    congress: int = Query(default=119, ge=1),
    session: int = Query(default=1, ge=1, le=2),
    limit: int = Query(default=10, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    repository: LegislativeRepository = Depends(get_repository),
) -> VoteBillListResponse:
    return await repository.vote_bills(congress=congress, session=session, limit=limit, offset=offset)


@app.get("/votes/house/{congress}/{session}/{roll_call_number}/members", response_model=VoteMemberListResponse)
async def house_vote_members(
    congress: int,
    session: int,
    roll_call_number: int,
    repository: LegislativeRepository = Depends(get_repository),
) -> VoteMemberListResponse:
    return await repository.vote_members(congress=congress, session=session, roll_call_number=roll_call_number)


@app.get("/votes/house", response_model=VoteExplorerResponse)
async def house_votes(
    congress: int = Query(default=119, ge=108),
    session: int = Query(default=1, ge=1, le=2),
    limit: int = Query(default=25, ge=1, le=100),
    repository: LegislativeRepository = Depends(get_repository),
) -> VoteExplorerResponse:
    return await repository.votes(congress=congress, session=session, limit=limit)


@app.get("/analytics", response_model=AnalyticsResponse)
async def analytics(repository: LegislativeRepository = Depends(get_repository)) -> AnalyticsResponse:
    return await repository.analytics()


app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets", check_dir=False), name="assets")


@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    if INDEX_FILE.exists() and "." not in Path(full_path).name:
        return FileResponse(INDEX_FILE)
    raise HTTPException(status_code=404, detail="Not found")
