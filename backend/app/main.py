from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings
from app.congress_client import CongressClient
from app.repository import LegislativeRepository
from app.schemas import AnalyticsResponse, BillDetail, HealthResponse, MemberProfile, MemberSummary, VoteExplorerResponse


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
            "/bills/{bill_id}",
            "/votes/house",
            "/analytics",
        ],
    }


@app.get("/health", response_model=HealthResponse)
async def health(repository: LegislativeRepository = Depends(get_repository)) -> HealthResponse:
    return HealthResponse(status="ok", data_mode=repository.data_mode)


@app.get("/members", response_model=list[MemberSummary])
async def search_members(
    query: str | None = None,
    state: str | None = Query(default=None, min_length=2, max_length=2),
    party: str | None = None,
    chamber: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    repository: LegislativeRepository = Depends(get_repository),
) -> list[MemberSummary]:
    return await repository.search_members(query=query, state=state, party=party, chamber=chamber, limit=limit)


@app.get("/members/{bioguide_id}", response_model=MemberProfile)
async def member_profile(
    bioguide_id: str,
    repository: LegislativeRepository = Depends(get_repository),
) -> MemberProfile:
    profile = await repository.member_profile(bioguide_id)
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
