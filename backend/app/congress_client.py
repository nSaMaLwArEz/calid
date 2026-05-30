from typing import Any

import httpx

from app.config import Settings
from app.schemas import Action, BillDetail, BillListResponse, BillSummary, Committee, Cosponsor, MemberListResponse, MemberSummary, Vote


class CongressClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.enabled = bool(settings.congress_api_key)

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.settings.congress_api_key:
            raise RuntimeError("CONGRESS_API_KEY is not configured.")

        query = {"api_key": self.settings.congress_api_key, "format": "json"}
        if params:
            query.update(params)

        async with httpx.AsyncClient(base_url=str(self.settings.congress_api_base_url), timeout=20) as client:
            response = await client.get(path, params=query)
            response.raise_for_status()
            return response.json()

    async def search_members(
        self,
        query: str | None,
        state: str | None,
        party: str | None,
        chamber: str | None,
        limit: int,
        offset: int = 0,
    ) -> MemberListResponse:
        has_filters = bool(query or state or party or chamber)
        if has_filters:
            return await self._filtered_member_search(
                query=query,
                state=state,
                party=party,
                chamber=chamber,
                limit=limit,
                offset=offset,
            )

        payload = await self._get("/member", params={"limit": limit, "offset": offset})
        raw_members = payload.get("members", [])
        return MemberListResponse(
            items=[self._parse_member(item) for item in raw_members[:limit]],
            limit=limit,
            offset=offset,
            total=self._pagination_total(payload),
        )

    async def bills(
        self,
        congress: int | None,
        bill_type: str | None,
        limit: int,
        offset: int = 0,
    ) -> BillListResponse:
        path = "/bill"
        if congress and bill_type:
            path = f"/bill/{congress}/{bill_type}"
        elif congress:
            path = f"/bill/{congress}"

        payload = await self._get(path, params={"limit": limit, "offset": offset})
        raw_bills = payload.get("bills", [])
        return BillListResponse(
            items=[self._parse_bill_summary(item) for item in raw_bills[:limit]],
            limit=limit,
            offset=offset,
            total=self._pagination_total(payload),
        )

    async def member(self, bioguide_id: str) -> MemberSummary | None:
        payload = await self._get(f"/member/{bioguide_id}")
        item = payload.get("member")
        return self._parse_member(item) if item else None

    async def sponsored_legislation(self, bioguide_id: str, limit: int = 20) -> list[BillSummary]:
        payload = await self._get(f"/member/{bioguide_id}/sponsored-legislation", {"limit": limit})
        return [self._parse_bill_summary(item) for item in payload.get("sponsoredLegislation", [])]

    async def cosponsored_legislation(self, bioguide_id: str, limit: int = 20) -> list[BillSummary]:
        payload = await self._get(f"/member/{bioguide_id}/cosponsored-legislation", {"limit": limit})
        return [self._parse_bill_summary(item) for item in payload.get("cosponsoredLegislation", [])]

    async def bill_detail(self, congress: int, bill_type: str, number: str) -> BillDetail:
        payload = await self._get(f"/bill/{congress}/{bill_type}/{number}")
        bill = payload.get("bill", {})
        base = self._parse_bill_summary(bill)

        actions_payload = await self._get(f"/bill/{congress}/{bill_type}/{number}/actions", {"limit": 100})
        cosponsors_payload = await self._get(f"/bill/{congress}/{bill_type}/{number}/cosponsors", {"limit": 100})
        committees_payload = await self._get(f"/bill/{congress}/{bill_type}/{number}/committees", {"limit": 100})
        summaries_payload = await self._get(f"/bill/{congress}/{bill_type}/{number}/summaries", {"limit": 10})

        sponsor = bill.get("sponsors", [{}])[0] if bill.get("sponsors") else None
        summaries = summaries_payload.get("summaries", [])

        return BillDetail(
            **base.model_dump(),
            sponsor=self._parse_member(sponsor) if sponsor else None,
            summary=summaries[0].get("text") if summaries else bill.get("summary"),
            cosponsors=[self._parse_cosponsor(item) for item in cosponsors_payload.get("cosponsors", [])],
            actions=[self._parse_action(item) for item in actions_payload.get("actions", [])],
            committees=[self._parse_committee(item) for item in committees_payload.get("committees", [])],
        )

    async def house_votes(self, congress: int, session: int, limit: int = 25) -> list[Vote]:
        payload = await self._get(f"/house-vote/{congress}/{session}", {"limit": limit})
        return [self._parse_vote(item, congress, session) for item in payload.get("houseRollCallVotes", [])]

    def _parse_member(self, item: dict[str, Any]) -> MemberSummary:
        terms = item.get("terms", {}).get("item", []) if isinstance(item.get("terms"), dict) else item.get("terms", [])
        latest_term = terms[-1] if terms else {}
        party = item.get("partyName") or latest_term.get("partyName") or item.get("party") or "Unknown"
        chamber = latest_term.get("chamber") or item.get("chamber") or "Unknown"

        return MemberSummary(
            bioguide_id=item.get("bioguideId") or item.get("bioguide_id") or item.get("id") or "",
            name=item.get("name") or item.get("directOrderName") or item.get("invertedOrderName") or "Unknown member",
            state=(item.get("state") or latest_term.get("stateCode") or "")[:2],
            party=party,
            chamber=chamber,
            district=str(item.get("district") or latest_term.get("district") or "") or None,
            image_url=item.get("depiction", {}).get("imageUrl") if isinstance(item.get("depiction"), dict) else None,
        )

    def _filter_members(
        self,
        members: list[MemberSummary],
        query: str | None,
        state: str | None,
        party: str | None,
        chamber: str | None,
    ) -> list[MemberSummary]:
        if query:
            members = [member for member in members if query.lower() in member.name.lower()]
        if state:
            members = [member for member in members if member.state.upper() == state.upper()]
        if party:
            members = [member for member in members if member.party.lower().startswith(party.lower())]
        if chamber:
            members = [member for member in members if member.chamber.lower() == chamber.lower()]
        return members

    async def _filtered_member_search(
        self,
        query: str | None,
        state: str | None,
        party: str | None,
        chamber: str | None,
        limit: int,
        offset: int,
    ) -> MemberListResponse:
        page_size = 250
        api_offset = 0
        matches: list[MemberSummary] = []
        total_available: int | None = None
        target_count = offset + limit

        while len(matches) < target_count:
            payload = await self._get("/member", params={"limit": page_size, "offset": api_offset})
            total_available = self._pagination_total(payload)
            raw_members = payload.get("members", [])
            if not raw_members:
                break

            page_members = [self._parse_member(item) for item in raw_members]
            matches.extend(self._filter_members(page_members, query=query, state=state, party=party, chamber=chamber))
            api_offset += page_size

            if total_available is not None and api_offset >= total_available:
                break

        scanned_everything = total_available is not None and api_offset >= total_available
        return MemberListResponse(
            items=matches[offset : offset + limit],
            limit=limit,
            offset=offset,
            total=len(matches) if scanned_everything else None,
        )

    def _parse_bill_summary(self, item: dict[str, Any]) -> BillSummary:
        congress = int(item.get("congress") or 0)
        bill_type = (item.get("type") or item.get("billType") or "").lower()
        number = str(item.get("number") or "")
        latest_action = item.get("latestAction") or {}

        return BillSummary(
            id=f"{congress}-{bill_type}-{number}",
            congress=congress,
            bill_type=bill_type,
            number=number,
            title=item.get("title") or "Untitled legislation",
            latest_action=latest_action.get("text") if isinstance(latest_action, dict) else None,
            latest_action_date=latest_action.get("actionDate") if isinstance(latest_action, dict) else None,
            policy_area=item.get("policyArea", {}).get("name") if isinstance(item.get("policyArea"), dict) else None,
            status=item.get("status"),
        )

    def _parse_action(self, item: dict[str, Any]) -> Action:
        return Action(
            date=item.get("actionDate"),
            text=item.get("text") or "",
            action_type=item.get("type"),
        )

    def _parse_cosponsor(self, item: dict[str, Any]) -> Cosponsor:
        return Cosponsor(
            bioguide_id=item.get("bioguideId"),
            name=item.get("fullName") or item.get("name") or "Unknown cosponsor",
            party=item.get("party"),
            state=item.get("state"),
            date=item.get("sponsorshipDate"),
            is_original_cosponsor=item.get("isOriginalCosponsor"),
        )

    def _parse_committee(self, item: dict[str, Any]) -> Committee:
        return Committee(
            name=item.get("name") or item.get("systemCode") or "Unknown committee",
            chamber=item.get("chamber"),
        )

    def _parse_vote(self, item: dict[str, Any], congress: int, session: int) -> Vote:
        return Vote(
            congress=congress,
            session=session,
            chamber="House",
            roll_call_number=int(item.get("rollCallNumber") or item.get("number") or 0),
            date=item.get("date") or item.get("voteDate"),
            question=item.get("question") or item.get("description") or "Roll-call vote",
            result=item.get("result"),
            source_url=item.get("url"),
        )

    def _pagination_total(self, payload: dict[str, Any]) -> int | None:
        pagination = payload.get("pagination")
        if not isinstance(pagination, dict):
            return None
        count = pagination.get("count")
        return int(count) if count is not None else None
