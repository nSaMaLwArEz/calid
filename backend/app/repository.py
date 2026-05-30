from app import demo_data
from app.congress_client import CongressClient
from app.schemas import AnalyticsResponse, BillDetail, BillListResponse, BillSummary, MemberListResponse, MemberProfile, MemberSummary, VoteExplorerResponse


class LegislativeRepository:
    def __init__(self, congress_client: CongressClient):
        self.congress_client = congress_client

    @property
    def data_mode(self) -> str:
        return "congress.gov" if self.congress_client.enabled else "demo"

    async def search_members(
        self,
        query: str | None = None,
        state: str | None = None,
        party: str | None = None,
        chamber: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> MemberListResponse:
        if self.congress_client.enabled:
            return await self.congress_client.search_members(query, state, party, chamber, limit, offset)

        members = demo_data.MEMBERS
        if query:
            members = [member for member in members if query.lower() in member.name.lower()]
        if state:
            members = [member for member in members if member.state.upper() == state.upper()]
        if party:
            members = [member for member in members if member.party.lower().startswith(party.lower())]
        if chamber:
            members = [member for member in members if member.chamber.lower() == chamber.lower()]
        total = len(members)
        return MemberListResponse(items=members[offset : offset + limit], limit=limit, offset=offset, total=total)

    async def bills(
        self,
        congress: int | None = 119,
        bill_type: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> BillListResponse:
        if self.congress_client.enabled:
            return await self.congress_client.bills(congress=congress, bill_type=bill_type, limit=limit, offset=offset)

        bills = [BillSummary(**bill.model_dump()) for bill in demo_data.BILLS]
        if congress:
            bills = [bill for bill in bills if bill.congress == congress]
        if bill_type:
            bills = [bill for bill in bills if bill.bill_type.lower() == bill_type.lower()]
        total = len(bills)
        return BillListResponse(items=bills[offset : offset + limit], limit=limit, offset=offset, total=total)

    async def member_profile(self, bioguide_id: str) -> MemberProfile | None:
        if self.congress_client.enabled:
            member = await self.congress_client.member(bioguide_id)
            if not member:
                return None
            sponsored = await self.congress_client.sponsored_legislation(bioguide_id)
            cosponsored = await self.congress_client.cosponsored_legislation(bioguide_id)
            return MemberProfile(
                **member.model_dump(),
                sponsored_bills=sponsored,
                cosponsored_bills=cosponsored,
                latest_actions=[],
                committees=[],
                bill_status_summaries=[self._status_line(bill) for bill in sponsored + cosponsored],
            )

        member = next((item for item in demo_data.MEMBERS if item.bioguide_id == bioguide_id), None)
        return demo_data.build_profile(member) if member else None

    async def bill_detail(self, bill_id: str) -> BillDetail | None:
        parts = bill_id.split("-")
        if len(parts) >= 3 and self.congress_client.enabled:
            congress = int(parts[0])
            bill_type = parts[1]
            number = parts[2]
            return await self.congress_client.bill_detail(congress, bill_type, number)

        return next((bill for bill in demo_data.BILLS if bill.id == bill_id), None)

    async def votes(self, congress: int = 119, session: int = 1, limit: int = 25) -> VoteExplorerResponse:
        note = (
            "Congress.gov supports beta House roll-call vote endpoints. "
            "Senate votes, voice votes, and some bill-specific voting contexts may require another data source."
        )
        if self.congress_client.enabled:
            votes = await self.congress_client.house_votes(congress, session, limit)
            return VoteExplorerResponse(votes=votes, note=note)

        return VoteExplorerResponse(votes=demo_data.VOTES[:limit], note=f"{note} Showing demo votes because live data is unavailable.")

    async def analytics(self) -> AnalyticsResponse:
        return AnalyticsResponse(**demo_data.ANALYTICS)

    def _status_line(self, bill: BillSummary) -> str:
        label = f"{bill.bill_type.upper()} {bill.number}"
        return f"{label}: {bill.status or bill.latest_action or 'Status unavailable'}"
