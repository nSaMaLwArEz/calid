from collections import defaultdict

from sqlalchemy import case, distinct, func, select
from sqlalchemy.orm import Session

from app import demo_data
from app.congress_client import CongressClient
from app.models import Bill, RollCallVote, VotePosition
from app.schemas import AnalyticsResponse, BillDetail, BillListResponse, BillSummary, MemberListResponse, MemberProfile, MemberSummary, MemberVotingProfile, MonthlyVoteSummary, Vote, VoteBillListResponse, VoteBillSummary, VoteExplorerResponse, VoteMemberListResponse
from app.schemas import AnalyticsCard, AnalyticsMetric, DashboardAnalyticsResponse, VoteTrendPoint
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
        if self.congress_client.enabled:
            pending = [
                self._etl_required_card(
                    "Analytics Require Vote Cache",
                    "Sync House vote rosters and bill/cosponsor ETL before this legacy endpoint can calculate live analytics.",
                )
            ]
            return AnalyticsResponse(
                most_active_legislators=pending,
                most_bipartisan_bills=pending,
                party_alignment=pending,
                topic_bills=pending,
                issue_focus_profiles=pending,
            )
        return AnalyticsResponse(**demo_data.ANALYTICS)

    async def dashboard_analytics(self, congress: int = 119, session: int = 1) -> DashboardAnalyticsResponse:
        note = "Analytics use cached House roll-call data when available. Bill topic/status summaries use cached bills or a live Congress.gov page sample."
        if self.db and has_cached_votes(self.db, congress, session):
            totals = self._cached_total_metrics(congress, session)
            return DashboardAnalyticsResponse(
                totals=totals,
                vote_participation_over_time=self._cached_vote_trends(congress, session),
                most_active_legislators=self._cached_most_active_legislators(congress, session),
                bills_by_policy_area=await self._bill_policy_metrics(congress),
                bills_by_status=await self._bill_status_metrics(congress),
                missed_vote_leaders=self._cached_missed_vote_leaders(congress, session),
                closest_votes=self._cached_closest_votes(congress, session),
                most_bipartisan_bills=self._bipartisan_metrics(),
                note=note,
            )

        if self.congress_client.enabled:
            return await self._live_uncached_dashboard(congress, session)

        bills = await self._sample_bills(congress, allow_demo=True)
        return DashboardAnalyticsResponse(
            totals=[
                AnalyticsMetric(label="Bills Sampled", value=len(bills), detail="Demo bill records loaded for this dashboard"),
                AnalyticsMetric(label="Roll-call Votes", value=len(demo_data.VOTES), detail="Demo vote records until House vote cache is synced"),
                AnalyticsMetric(label="Vote Positions", value=len(demo_data.VOTE_MEMBERS), detail="Demo vote positions until House vote cache is synced"),
                AnalyticsMetric(label="Legislators", value=len(demo_data.MEMBERS), detail="Demo members"),
            ],
            vote_participation_over_time=[
                VoteTrendPoint(month=item.month, participated=item.participated, missed=item.missed, total_votes=item.total)
                for item in self._monthly_summary(demo_data.VOTES, demo_data.VOTES)
            ],
            most_active_legislators=self._cards_to_metrics(demo_data.ANALYTICS["most_active_legislators"]),
            bills_by_policy_area=self._group_bills(bills, "policy_area"),
            bills_by_status=self._group_bills(bills, "status"),
            missed_vote_leaders=[
                AnalyticsMetric(label=member.name, value=1 if member.vote.lower() == "not voting" else 0, detail=member.vote)
                for member in demo_data.VOTE_MEMBERS
            ],
            closest_votes=[
                AnalyticsMetric(label=vote.question, value=abs(vote.yea - vote.nay), detail=f"Yea {vote.yea}, Nay {vote.nay}")
                for vote in demo_data.VOTE_BILLS
            ],
            most_bipartisan_bills=self._bipartisan_metrics(),
            note="Demo analytics are active because CONGRESS_API_KEY is not configured.",
        )

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

    def _cached_total_metrics(self, congress: int, session: int) -> list[AnalyticsMetric]:
        vote_count = self.db.scalar(
            select(func.count(RollCallVote.id)).where(RollCallVote.congress == congress, RollCallVote.session == session)
        ) or 0
        position_count = self.db.scalar(
            select(func.count(VotePosition.id))
            .join(RollCallVote)
            .where(RollCallVote.congress == congress, RollCallVote.session == session)
        ) or 0
        legislator_count = self.db.scalar(
            select(func.count(distinct(VotePosition.member_bioguide_id)))
            .join(RollCallVote)
            .where(RollCallVote.congress == congress, RollCallVote.session == session)
        ) or 0
        bill_count = self.db.scalar(select(func.count(Bill.id)).where(Bill.congress == congress)) or 0
        return [
            AnalyticsMetric(label="Legislators", value=legislator_count, detail="Distinct members with cached vote positions"),
            AnalyticsMetric(label="Bills", value=bill_count, detail="Bills stored locally"),
            AnalyticsMetric(label="Roll-call Votes", value=vote_count, detail="Cached House roll-call votes"),
            AnalyticsMetric(label="Vote Positions", value=position_count, detail="Cached member vote positions"),
        ]

    def _cached_vote_trends(self, congress: int, session: int) -> list[VoteTrendPoint]:
        rows = self.db.execute(
            select(
                func.substr(RollCallVote.date, 1, 7).label("month"),
                func.count(distinct(RollCallVote.id)).label("total_votes"),
                func.sum(case((func.lower(VotePosition.vote).in_(["yea", "aye", "yes", "nay", "no", "present"]), 1), else_=0)).label("participated"),
                func.sum(case((func.lower(VotePosition.vote).in_(["not voting", "not-voting", "absent", "missing"]), 1), else_=0)).label("missed"),
            )
            .join(VotePosition, VotePosition.roll_call_vote_id == RollCallVote.id)
            .where(RollCallVote.congress == congress, RollCallVote.session == session, RollCallVote.date.is_not(None))
            .group_by("month")
            .order_by("month")
        ).all()
        return [
            VoteTrendPoint(month=row.month, participated=int(row.participated or 0), missed=int(row.missed or 0), total_votes=int(row.total_votes or 0))
            for row in rows
        ]

    def _cached_most_active_legislators(self, congress: int, session: int) -> list[AnalyticsMetric]:
        rows = self.db.execute(
            select(
                VotePosition.member_name,
                func.count(VotePosition.id).label("participated"),
            )
            .join(RollCallVote)
            .where(
                RollCallVote.congress == congress,
                RollCallVote.session == session,
                func.lower(VotePosition.vote).not_in(["not voting", "not-voting", "absent", "missing"]),
            )
            .group_by(VotePosition.member_name)
            .order_by(func.count(VotePosition.id).desc())
            .limit(10)
        ).all()
        return [
            AnalyticsMetric(label=row.member_name, value=int(row.participated), detail="Participated roll-call votes in cache")
            for row in rows
        ]

    def _cached_missed_vote_leaders(self, congress: int, session: int) -> list[AnalyticsMetric]:
        rows = self.db.execute(
            select(VotePosition.member_name, func.count(VotePosition.id).label("missed"))
            .join(RollCallVote)
            .where(
                RollCallVote.congress == congress,
                RollCallVote.session == session,
                func.lower(VotePosition.vote).in_(["not voting", "not-voting", "absent", "missing"]),
            )
            .group_by(VotePosition.member_name)
            .order_by(func.count(VotePosition.id).desc())
            .limit(10)
        ).all()
        return [AnalyticsMetric(label=row.member_name, value=int(row.missed), detail="Cached not voting records") for row in rows]

    def _cached_closest_votes(self, congress: int, session: int) -> list[AnalyticsMetric]:
        items, _total = cached_vote_bills(self.db, congress, session, limit=250, offset=0)
        closest = sorted(items, key=lambda vote: abs(vote.yea - vote.nay))[:10]
        return [
            AnalyticsMetric(label=f"Roll {vote.roll_call_number}: {vote.question}", value=abs(vote.yea - vote.nay), detail=f"Yea {vote.yea}, Nay {vote.nay}")
            for vote in closest
        ]

    async def _live_uncached_dashboard(self, congress: int, session: int) -> DashboardAnalyticsResponse:
        try:
            members = await self.congress_client.search_members(None, None, None, None, limit=1, offset=0)
            bill_response = await self.congress_client.bills(congress=congress, bill_type=None, limit=100, offset=0)
            votes, total_votes = await self.congress_client.house_vote_page(congress, session, limit=1, offset=0)
            bill_total = bill_response.total if bill_response.total is not None else len(bill_response.items)
            member_total = members.total if members.total is not None else len(members.items)
            vote_total = total_votes if total_votes is not None else len(votes)
            bills = bill_response.items
            note = (
                "Connected to Congress.gov, but the House vote roster cache is empty. "
                "Run /admin/sync/house-votes to populate historical vote counts, participation trends, missed votes, and member-level rosters."
            )
        except Exception:
            return DashboardAnalyticsResponse(
                totals=[
                    AnalyticsMetric(label="Congress.gov", value="error", detail="Live probe failed"),
                    AnalyticsMetric(label="Roll-call Cache", value=0, detail="No cached vote history is available"),
                ],
                vote_participation_over_time=[],
                most_active_legislators=[],
                bills_by_policy_area=[],
                bills_by_status=[],
                missed_vote_leaders=[],
                closest_votes=[],
                most_bipartisan_bills=[],
                note="Congress.gov is configured, but the live analytics probe failed. Check /diagnostics/data for the redacted upstream error.",
            )

        return DashboardAnalyticsResponse(
            totals=[
                AnalyticsMetric(label="Legislators", value=member_total, detail="Live Congress.gov member count"),
                AnalyticsMetric(label="Bills", value=bill_total, detail="Live Congress.gov bill count for this Congress"),
                AnalyticsMetric(label="House Roll-call Votes", value=vote_total, detail="Live Congress.gov vote count for this Congress/session"),
                AnalyticsMetric(label="Cached Vote Positions", value=0, detail="Database cache has not been synced yet"),
            ],
            vote_participation_over_time=[],
            most_active_legislators=[],
            bills_by_policy_area=self._group_bills(bills, "policy_area"),
            bills_by_status=self._group_bills(bills, "status"),
            missed_vote_leaders=[],
            closest_votes=[],
            most_bipartisan_bills=self._bipartisan_metrics(),
            note=note,
        )

    async def _sample_bills(self, congress: int, allow_demo: bool = False) -> list[BillSummary]:
        if self.db:
            cached = self.db.scalars(select(Bill).where(Bill.congress == congress).limit(250)).all()
            if cached:
                return [
                    BillSummary(
                        id=bill.id,
                        congress=bill.congress,
                        bill_type=bill.bill_type,
                        number=bill.number,
                        title=bill.title,
                        latest_action=bill.latest_action,
                        latest_action_date=bill.latest_action_date,
                        policy_area=bill.policy_area,
                    )
                    for bill in cached
                ]
        try:
            response = await self.bills(congress=congress, limit=100, offset=0)
            return response.items
        except Exception:
            if not allow_demo:
                return []
            return [BillSummary(**bill.model_dump()) for bill in demo_data.BILLS]

    async def _bill_policy_metrics(self, congress: int) -> list[AnalyticsMetric]:
        return self._group_bills(await self._sample_bills(congress, allow_demo=not self.congress_client.enabled), "policy_area")

    async def _bill_status_metrics(self, congress: int) -> list[AnalyticsMetric]:
        return self._group_bills(await self._sample_bills(congress, allow_demo=not self.congress_client.enabled), "status")

    def _group_bills(self, bills: list[BillSummary], field: str) -> list[AnalyticsMetric]:
        counts: dict[str, int] = defaultdict(int)
        for bill in bills:
            value = getattr(bill, field) or "Unavailable"
            counts[value] += 1
        return [AnalyticsMetric(label=label, value=value) for label, value in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:10]]

    def _bipartisan_metrics(self) -> list[AnalyticsMetric]:
        if self.congress_client.enabled:
            return [
                AnalyticsMetric(
                    label="Cosponsor Mix Unavailable",
                    value=0,
                    detail="This needs cosponsor-party ETL before it can be calculated without demo data.",
                )
            ]
        return self._cards_to_metrics(demo_data.ANALYTICS["most_bipartisan_bills"])

    def _cards_to_metrics(self, cards) -> list[AnalyticsMetric]:
        return [AnalyticsMetric(label=item.label, value=item.value, detail=item.detail) for item in cards]

    def _etl_required_card(self, label: str, detail: str) -> AnalyticsCard:
        return AnalyticsCard(label=label, value=0, detail=detail)
