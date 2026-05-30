from typing import Any

import httpx

from app.config import Settings
from app.schemas import Action, BillDetail, BillSummary, Committee, Cosponsor, MemberSummary, Vote


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
    ) -> list[MemberSummary]:
        params: dict[str, Any] = {"limit": limit}
        if query:
            params["query"] = query
        if state:
            params["state"] = state.upper()
        if party:
            params["party"] = party
        if chamber:
            params["chamber"] = chamber

        payload = await self._get("/member", params=params)
        raw_members = payload.get("members", [])
        return [self._parse_member(item) for item in raw_members[:limit]]

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
