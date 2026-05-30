from collections import defaultdict

from sqlalchemy.orm import Session

from app import demo_data
from app.congress_client import CongressClient
from app.schemas import AnalyticsResponse, BillDetail, BillListResponse, BillSummary, MemberListResponse, MemberProfile, MemberSummary, MemberVotingProfile, MonthlyVoteSummary, Vote, VoteBillListResponse, VoteBillSummary, VoteExplorerResponse, VoteMemberListResponse
from app.vote_cache import cached_member_voting_profile, cached_vote_bills, cached_vote_members, has_cached_votes


class LegislativeRepository:
    def __init__(self, congress_client: CongressClient, db: Session | None = None):
        self.congress_client = congress_client
        self.db = db

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

    async def vote_bills(self, congress: int = 119, session: int = 1, limit: int = 10, offset: int = 0) -> VoteBillListResponse:
        note = "Vote counts use cached database records when available, then Congress.gov House roll-call data."
        if self.db and has_cached_votes(self.db, congress, session):
            items, total = cached_vote_bills(self.db, congress, session, limit, offset)
            return VoteBillListResponse(
                items=items,
                limit=limit,
                offset=offset,
                total=total,
                note="Vote counts are computed from cached House roll-call rosters in the database.",
            )

        if self.congress_client.enabled:
            votes, total = await self.congress_client.house_vote_page(congress, session, limit, offset)
            items: list[VoteBillSummary] = []
            for vote in votes:
                try:
                    detail, _members = await self.congress_client.house_vote_members(congress, session, vote.roll_call_number)
                    items.append(detail)
                except Exception:
                    items.append(VoteBillSummary(**vote.model_dump()))
            return VoteBillListResponse(items=items, limit=limit, offset=offset, total=total, note=note)

        return VoteBillListResponse(items=demo_data.VOTE_BILLS[:limit], limit=limit, offset=offset, total=len(demo_data.VOTE_BILLS), note=f"{note} Showing demo vote data.")

    async def vote_members(self, congress: int, session: int, roll_call_number: int) -> VoteMemberListResponse:
        note = "Member vote rosters use cached database records when available, then Congress.gov."
        if self.db and has_cached_votes(self.db, congress, session):
            vote, members = cached_vote_members(self.db, congress, session, roll_call_number)
            if vote:
                return VoteMemberListResponse(vote=vote, members=members, note="Member vote roster is loaded from the database cache.")

        if self.congress_client.enabled:
            vote, members = await self.congress_client.house_vote_members(congress, session, roll_call_number)
            return VoteMemberListResponse(vote=vote, members=members, note=note)

        vote = next((item for item in demo_data.VOTE_BILLS if item.roll_call_number == roll_call_number), demo_data.VOTE_BILLS[0])
        return VoteMemberListResponse(vote=vote, members=demo_data.VOTE_MEMBERS, note=f"{note} Showing demo vote data.")

    async def member_voting_profile(
        self,
        bioguide_id: str,
        congress: int = 119,
        session: int = 1,
        limit: int = 250,
    ) -> MemberVotingProfile | None:
        member = await self.member_profile(bioguide_id)
        if not member:
            return None

        if self.db:
            cached_profile = cached_member_voting_profile(self.db, MemberSummary(**member.model_dump()), congress, session)
            if cached_profile:
                return cached_profile

        note = "Voting history uses Congress.gov beta House roll-call vote rosters. Senate votes and non-roll-call votes require another data source."
        votes: list[Vote] = []
        roll_calls: list[Vote] = []
        total_votes = 0
        available_votes: int | None = None

        if self.congress_client.enabled:
            if member.chamber.lower() != "house":
                return MemberVotingProfile(
                    member=MemberSummary(**member.model_dump()),
                    votes=[],
                    monthly=[],
                    total_votes=0,
                    scanned_votes=0,
                    available_votes=None,
                    participated=0,
                    missed=0,
                    note="Congress.gov currently exposes detailed roll-call voting through the House vote API. Senate vote detail requires another data source.",
                )
            roll_calls, total = await self.congress_client.house_vote_page(congress, session, limit, 0)
            available_votes = total
            total_votes = len(roll_calls)
            for roll_call in roll_calls:
                try:
                    detail, members = await self.congress_client.house_vote_members(congress, session, roll_call.roll_call_number)
                    position = self._member_position(members, bioguide_id, member.name)
                    if position:
                        votes.append(
                            Vote(
                                **detail.model_dump(exclude={"yea", "nay", "abstained", "not_voting", "member_position"}),
                                member_position=position,
                            )
                        )
                except Exception:
                    continue
        else:
            roll_calls = demo_data.VOTES
            total_votes = len(roll_calls)
            votes = [
                Vote(**vote.model_dump(exclude={"member_position"}), member_position=self._member_position(demo_data.VOTE_MEMBERS, bioguide_id, member.name))
                for vote in demo_data.VOTES
            ]
            votes = [vote for vote in votes if vote.member_position]

        participated = len([vote for vote in votes if self._participated(vote.member_position)])
        missed = max(total_votes - participated, 0)
        return MemberVotingProfile(
            member=MemberSummary(**member.model_dump()),
            votes=votes,
            monthly=self._monthly_summary(roll_calls, votes),
            total_votes=total_votes,
            scanned_votes=total_votes,
            available_votes=available_votes,
            participated=participated,
            missed=missed,
            note=note,
        )

    async def analytics(self) -> AnalyticsResponse:
        return AnalyticsResponse(**demo_data.ANALYTICS)

    def _status_line(self, bill: BillSummary) -> str:
        label = f"{bill.bill_type.upper()} {bill.number}"
        return f"{label}: {bill.status or bill.latest_action or 'Status unavailable'}"

    def _member_position(self, members, bioguide_id: str, name: str) -> str | None:
        for member in members:
            if member.bioguide_id == bioguide_id or member.name.lower() == name.lower():
                return member.vote
        return None

    def _participated(self, position: str | None) -> bool:
        if not position:
            return False
        return position.strip().lower() not in {"not voting", "not-voting", "absent", "missing"}

    def _monthly_summary(self, roll_calls: list[Vote], member_votes: list[Vote]) -> list[MonthlyVoteSummary]:
        total_by_month: dict[str, int] = defaultdict(int)
        participated_by_month: dict[str, int] = defaultdict(int)
        for vote in roll_calls:
            if vote.date:
                total_by_month[vote.date[:7]] += 1

        for vote in member_votes:
            if vote.date and self._participated(vote.member_position):
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
