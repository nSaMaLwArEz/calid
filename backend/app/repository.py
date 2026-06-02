from collections import defaultdict
from datetime import date

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app import demo_data
from app.congress_client import CongressClient
from app.models import Bill, RollCallVote, VotePosition
from app.schemas import AnalyticsResponse, BillDetail, BillListResponse, BillSummary, MemberListResponse, MemberProfile, MemberSummary, MemberVotingProfile, MonthlyVoteSummary, Vote, VoteBillListResponse, VoteBillSummary, VoteExplorerResponse, VoteMemberListResponse
from app.schemas import AnalyticsCard, AnalyticsDateRange, AnalyticsMetric, DashboardAnalyticsResponse, VoteTrendPoint
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

    async def dashboard_analytics(
        self,
        congress: int = 119,
        session: int = 1,
        start_date: date | None = None,
        end_date: date | None = None,
        group_by: str = "month",
    ) -> DashboardAnalyticsResponse:
        start_date, end_date = self._resolved_date_range(congress, start_date, end_date)
        note = "Analytics use cached House roll-call data when available. Bill topic/status summaries use cached bills or a live Congress.gov page sample."
        if self.db and has_cached_votes(self.db, congress, session):
            totals = self._cached_total_metrics(congress, session, start_date, end_date)
            return DashboardAnalyticsResponse(
                totals=totals,
                vote_participation_over_time=self._cached_vote_trends(congress, session, start_date, end_date, group_by),
                most_active_legislators=self._cached_most_active_legislators(congress, session, start_date, end_date),
                bills_by_policy_area=await self._bill_policy_metrics(congress, start_date, end_date),
                bills_by_status=await self._bill_status_metrics(congress, start_date, end_date),
                missed_vote_leaders=self._cached_missed_vote_leaders(congress, session, start_date, end_date),
                closest_votes=self._cached_closest_votes(congress, session, start_date, end_date),
                most_bipartisan_bills=self._bipartisan_metrics(),
                date_range=self._date_range_model(start_date, end_date, group_by),
                note=note,
            )

        if self.congress_client.enabled:
            return await self._live_uncached_dashboard(congress, session, start_date, end_date, group_by)

        bills = await self._sample_bills(congress, allow_demo=True)
        demo_votes = [vote for vote in demo_data.VOTES if self._date_string_in_range(vote.date, start_date, end_date)]
        demo_member_votes = [vote for vote in demo_votes if vote.member_position]
        return DashboardAnalyticsResponse(
            totals=[
                AnalyticsMetric(label="Bills Sampled", value=len(bills), detail="Demo bill records loaded for this dashboard"),
                AnalyticsMetric(label="Roll-call Votes", value=len(demo_votes), detail="Demo vote records until House vote cache is synced"),
                AnalyticsMetric(label="Vote Positions", value=len(demo_data.VOTE_MEMBERS), detail="Demo vote positions until House vote cache is synced"),
                AnalyticsMetric(label="Legislators", value=len(demo_data.MEMBERS), detail="Demo members"),
            ],
            vote_participation_over_time=[
                VoteTrendPoint(month=item.month, participated=item.participated, missed=item.missed, total_votes=item.total)
                for item in self._summary_by_period(demo_votes, demo_member_votes, group_by, congress)
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
            date_range=self._date_range_model(start_date, end_date, group_by),
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

    def _summary_by_period(self, roll_calls: list[Vote], member_votes: list[Vote], group_by: str, congress: int) -> list[MonthlyVoteSummary]:
        total_by_period: dict[str, int] = defaultdict(int)
        participated_by_period: dict[str, int] = defaultdict(int)
        for vote in roll_calls:
            parsed = self._parse_date_string(vote.date)
            if parsed:
                total_by_period[self._period_label(parsed, group_by, congress)] += 1

        for vote in member_votes:
            parsed = self._parse_date_string(vote.date)
            if parsed and self._participated(vote.member_position):
                participated_by_period[self._period_label(parsed, group_by, congress)] += 1

        return [
            MonthlyVoteSummary(
                month=period,
                participated=participated_by_period.get(period, 0),
                total=total,
                missed=max(total - participated_by_period.get(period, 0), 0),
            )
            for period, total in sorted(total_by_period.items())
        ]

    def _resolved_date_range(self, congress: int, start_date: date | None, end_date: date | None) -> tuple[date, date]:
        congress_start, congress_end = self._congress_date_range(congress)
        start = start_date or congress_start
        end = end_date or congress_end
        if end < start:
            return end, start
        return start, end

    def _congress_date_range(self, congress: int) -> tuple[date, date]:
        start_year = 1789 + ((congress - 1) * 2)
        return date(start_year, 1, 3), date(start_year + 2, 1, 2)

    def _date_range_model(self, start_date: date, end_date: date, group_by: str) -> AnalyticsDateRange:
        return AnalyticsDateRange(start_date=start_date.isoformat(), end_date=end_date.isoformat(), group_by=group_by)

    def _vote_date_conditions(self, congress: int, session: int, start_date: date, end_date: date):
        return (
            RollCallVote.congress == congress,
            RollCallVote.session == session,
            RollCallVote.date >= start_date,
            RollCallVote.date <= end_date,
        )

    def _bill_date_conditions(self, congress: int, start_date: date, end_date: date):
        return (
            Bill.congress == congress,
            Bill.latest_action_date >= start_date.isoformat(),
            Bill.latest_action_date <= end_date.isoformat(),
        )

    def _period_label(self, value: date, group_by: str, congress: int) -> str:
        if group_by == "calendar_year":
            return str(value.year)
        if group_by == "congress_year":
            congress_start, _congress_end = self._congress_date_range(congress)
            second_year_start = date(congress_start.year + 1, 1, 3)
            year_number = 1 if value < second_year_start else 2
            return f"Year {year_number} ({value.year})"
        return value.strftime("%Y-%m")

    def _trend_points(
        self,
        total_votes_by_period: dict[str, set[int]],
        participated_by_period: dict[str, int],
        missed_by_period: dict[str, int],
    ) -> list[VoteTrendPoint]:
        return [
            VoteTrendPoint(
                month=period,
                participated=participated_by_period.get(period, 0),
                missed=missed_by_period.get(period, 0),
                total_votes=len(vote_ids),
            )
            for period, vote_ids in sorted(total_votes_by_period.items())
        ]

    def _date_string_in_range(self, value: str | None, start_date: date, end_date: date) -> bool:
        parsed = self._parse_date_string(value)
        return bool(parsed and start_date <= parsed <= end_date)

    def _parse_date_string(self, value: str | None) -> date | None:
        if not value:
            return None
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None

    def _cached_total_metrics(self, congress: int, session: int, start_date: date, end_date: date) -> list[AnalyticsMetric]:
        vote_conditions = self._vote_date_conditions(congress, session, start_date, end_date)
        vote_count = self.db.scalar(
            select(func.count(RollCallVote.id)).where(*vote_conditions)
        ) or 0
        position_count = self.db.scalar(
            select(func.count(VotePosition.id))
            .join(RollCallVote)
            .where(*vote_conditions)
        ) or 0
        legislator_count = self.db.scalar(
            select(func.count(distinct(VotePosition.member_bioguide_id)))
            .join(RollCallVote)
            .where(*vote_conditions)
        ) or 0
        bill_count = self.db.scalar(select(func.count(Bill.id)).where(*self._bill_date_conditions(congress, start_date, end_date))) or 0
        return [
            AnalyticsMetric(label="Legislators", value=legislator_count, detail="Distinct members with cached vote positions"),
            AnalyticsMetric(label="Bills", value=bill_count, detail="Bills stored locally in selected date range"),
            AnalyticsMetric(label="Roll-call Votes", value=vote_count, detail="Cached House roll-call votes in selected date range"),
            AnalyticsMetric(label="Vote Positions", value=position_count, detail="Cached member vote positions in selected date range"),
        ]

    def _cached_vote_trends(self, congress: int, session: int, start_date: date, end_date: date, group_by: str) -> list[VoteTrendPoint]:
        rows = self.db.execute(
            select(
                RollCallVote.id,
                RollCallVote.date,
                VotePosition.vote,
            )
            .join(VotePosition, VotePosition.roll_call_vote_id == RollCallVote.id)
            .where(*self._vote_date_conditions(congress, session, start_date, end_date), RollCallVote.date.is_not(None))
            .order_by(RollCallVote.date)
        ).all()
        total_votes_by_period: dict[str, set[int]] = defaultdict(set)
        participated_by_period: dict[str, int] = defaultdict(int)
        missed_by_period: dict[str, int] = defaultdict(int)
        for row in rows:
            label = self._period_label(row.date, group_by, congress)
            total_votes_by_period[label].add(row.id)
            if self._participated(row.vote):
                participated_by_period[label] += 1
            else:
                missed_by_period[label] += 1
        return self._trend_points(total_votes_by_period, participated_by_period, missed_by_period)

    def _cached_most_active_legislators(self, congress: int, session: int, start_date: date, end_date: date) -> list[AnalyticsMetric]:
        rows = self.db.execute(
            select(
                VotePosition.member_name,
                func.count(VotePosition.id).label("participated"),
            )
            .join(RollCallVote)
            .where(
                *self._vote_date_conditions(congress, session, start_date, end_date),
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

    def _cached_missed_vote_leaders(self, congress: int, session: int, start_date: date, end_date: date) -> list[AnalyticsMetric]:
        rows = self.db.execute(
            select(VotePosition.member_name, func.count(VotePosition.id).label("missed"))
            .join(RollCallVote)
            .where(
                *self._vote_date_conditions(congress, session, start_date, end_date),
                func.lower(VotePosition.vote).in_(["not voting", "not-voting", "absent", "missing"]),
            )
            .group_by(VotePosition.member_name)
            .order_by(func.count(VotePosition.id).desc())
            .limit(10)
        ).all()
        return [AnalyticsMetric(label=row.member_name, value=int(row.missed), detail="Cached not voting records") for row in rows]

    def _cached_closest_votes(self, congress: int, session: int, start_date: date, end_date: date) -> list[AnalyticsMetric]:
        items, _total = cached_vote_bills(self.db, congress, session, limit=250, offset=0)
        items = [item for item in items if self._date_string_in_range(item.date, start_date, end_date)]
        closest = sorted(items, key=lambda vote: abs(vote.yea - vote.nay))[:10]
        return [
            AnalyticsMetric(label=f"Roll {vote.roll_call_number}: {vote.question}", value=abs(vote.yea - vote.nay), detail=f"Yea {vote.yea}, Nay {vote.nay}")
            for vote in closest
        ]

    async def _live_uncached_dashboard(self, congress: int, session: int, start_date: date, end_date: date, group_by: str) -> DashboardAnalyticsResponse:
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
                date_range=self._date_range_model(start_date, end_date, group_by),
                note="Congress.gov is configured, but the live analytics probe failed. Check /diagnostics/data for the redacted upstream error.",
            )

        return DashboardAnalyticsResponse(
            totals=[
                AnalyticsMetric(label="Legislators", value=member_total, detail="Live Congress.gov member count"),
                AnalyticsMetric(label="Bills", value=bill_total, detail="Live Congress.gov bill count for this Congress"),
                AnalyticsMetric(label="House Roll-call Votes", value=vote_total, detail="Live Congress.gov vote count for this Congress/session; date-filtered counts require cached rosters"),
                AnalyticsMetric(label="Cached Vote Positions", value=0, detail="Database cache has not been synced yet"),
            ],
            vote_participation_over_time=[],
            most_active_legislators=[],
            bills_by_policy_area=self._group_bills(bills, "policy_area"),
            bills_by_status=self._group_bills(bills, "status"),
            missed_vote_leaders=[],
            closest_votes=[],
            most_bipartisan_bills=self._bipartisan_metrics(),
            date_range=self._date_range_model(start_date, end_date, group_by),
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
