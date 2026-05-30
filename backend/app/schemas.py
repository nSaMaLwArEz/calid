from pydantic import BaseModel, ConfigDict


class MemberSummary(BaseModel):
    bioguide_id: str
    name: str
    state: str
    party: str
    chamber: str
    district: str | None = None
    image_url: str | None = None


class Action(BaseModel):
    date: str | None = None
    text: str
    action_type: str | None = None


class Committee(BaseModel):
    name: str
    chamber: str | None = None
    rank: str | None = None


class BillSummary(BaseModel):
    id: str
    congress: int
    bill_type: str
    number: str
    title: str
    latest_action: str | None = None
    latest_action_date: str | None = None
    policy_area: str | None = None
    status: str | None = None


class Cosponsor(BaseModel):
    bioguide_id: str | None = None
    name: str
    party: str | None = None
    state: str | None = None
    date: str | None = None
    is_original_cosponsor: bool | None = None


class BillDetail(BillSummary):
    sponsor: MemberSummary | None = None
    cosponsors: list[Cosponsor] = []
    summary: str | None = None
    actions: list[Action] = []
    committees: list[Committee] = []


class MemberProfile(MemberSummary):
    sponsored_bills: list[BillSummary]
    cosponsored_bills: list[BillSummary]
    latest_actions: list[Action]
    committees: list[Committee]
    bill_status_summaries: list[str]


class Vote(BaseModel):
    congress: int
    session: int
    chamber: str
    roll_call_number: int
    date: str | None = None
    question: str
    result: str | None = None
    bill_id: str | None = None
    member_position: str | None = None
    source_url: str | None = None


class VoteExplorerResponse(BaseModel):
    votes: list[Vote]
    note: str


class AnalyticsCard(BaseModel):
    label: str
    value: str | int | float
    detail: str | None = None


class AnalyticsResponse(BaseModel):
    most_active_legislators: list[AnalyticsCard]
    most_bipartisan_bills: list[AnalyticsCard]
    party_alignment: list[AnalyticsCard]
    topic_bills: list[AnalyticsCard]
    issue_focus_profiles: list[AnalyticsCard]


class HealthResponse(BaseModel):
    status: str
    data_mode: str

    model_config = ConfigDict(from_attributes=True)
