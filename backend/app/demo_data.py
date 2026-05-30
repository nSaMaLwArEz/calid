from app.schemas import Action, AnalyticsCard, BillDetail, BillSummary, Committee, Cosponsor, MemberProfile, MemberSummary, Vote


MEMBERS = [
    MemberSummary(
        bioguide_id="D000624",
        name="Tammy Duckworth",
        state="IL",
        party="Democratic",
        chamber="Senate",
        image_url="https://www.congress.gov/img/member/d000624_200.jpg",
    ),
    MemberSummary(
        bioguide_id="G000577",
        name="Mike Gallagher",
        state="WI",
        party="Republican",
        chamber="House",
        district="8",
        image_url="https://www.congress.gov/img/member/g000577_200.jpg",
    ),
    MemberSummary(
        bioguide_id="J000298",
        name="Pramila Jayapal",
        state="WA",
        party="Democratic",
        chamber="House",
        district="7",
        image_url="https://www.congress.gov/img/member/j000298_200.jpg",
    ),
]

SPONSOR = MEMBERS[0]

BILLS = [
    BillDetail(
        id="119-s-101",
        congress=119,
        bill_type="s",
        number="101",
        title="Veterans Care Access Improvement Act",
        policy_area="Veterans",
        status="Introduced",
        latest_action="Read twice and referred to the Committee on Veterans' Affairs.",
        latest_action_date="2025-01-15",
        sponsor=SPONSOR,
        summary="Expands access to community care appointments and improves digital scheduling for veterans.",
        cosponsors=[
            Cosponsor(name="Jane Smith", party="Republican", state="ME", date="2025-01-21"),
            Cosponsor(name="Alex Rivera", party="Democratic", state="CA", date="2025-01-22"),
        ],
        actions=[
            Action(date="2025-01-15", text="Introduced in Senate.", action_type="IntroReferral"),
            Action(date="2025-01-15", text="Referred to the Committee on Veterans' Affairs.", action_type="Committee"),
        ],
        committees=[Committee(name="Senate Veterans' Affairs", chamber="Senate")],
    ),
    BillDetail(
        id="119-hr-208",
        congress=119,
        bill_type="hr",
        number="208",
        title="Cybersecurity Workforce Pipeline Act",
        policy_area="Cybersecurity",
        status="Reported by committee",
        latest_action="Ordered to be reported by voice vote.",
        latest_action_date="2025-03-04",
        sponsor=MEMBERS[1],
        summary="Creates grants for community colleges and veterans programs to expand cybersecurity workforce training.",
        cosponsors=[
            Cosponsor(name="Tammy Duckworth", party="Democratic", state="IL", date="2025-02-03"),
            Cosponsor(name="Morgan Lee", party="Republican", state="UT", date="2025-02-08"),
        ],
        actions=[
            Action(date="2025-01-28", text="Introduced in House.", action_type="IntroReferral"),
            Action(date="2025-03-04", text="Ordered to be reported by voice vote.", action_type="Committee"),
        ],
        committees=[Committee(name="House Homeland Security", chamber="House")],
    ),
    BillDetail(
        id="119-hr-812",
        congress=119,
        bill_type="hr",
        number="812",
        title="Education Data Privacy Modernization Act",
        policy_area="Education",
        status="Passed House",
        latest_action="Received in the Senate and read twice.",
        latest_action_date="2025-04-10",
        sponsor=MEMBERS[2],
        summary="Updates privacy requirements for educational technology vendors and school data systems.",
        cosponsors=[
            Cosponsor(name="Chris Nguyen", party="Democratic", state="OR", date="2025-02-12"),
            Cosponsor(name="Pat O'Neill", party="Republican", state="PA", date="2025-02-13"),
        ],
        actions=[
            Action(date="2025-02-06", text="Introduced in House.", action_type="IntroReferral"),
            Action(date="2025-04-09", text="Passed/agreed to in House.", action_type="Floor"),
            Action(date="2025-04-10", text="Received in the Senate.", action_type="ResolvingDifferences"),
        ],
        committees=[Committee(name="House Education and Workforce", chamber="House")],
    ),
]

VOTES = [
    Vote(
        congress=119,
        session=1,
        chamber="House",
        roll_call_number=42,
        date="2025-04-09",
        question="On Passage: Education Data Privacy Modernization Act",
        result="Passed",
        bill_id="119-hr-812",
        member_position="Yea",
        source_url="https://api.congress.gov/v3/house-vote/119/1/42",
    )
]


def build_profile(member: MemberSummary) -> MemberProfile:
    sponsored = [bill for bill in BILLS if bill.sponsor and bill.sponsor.bioguide_id == member.bioguide_id]
    cosponsored = [
        bill
        for bill in BILLS
        if any(cosponsor.name == member.name or cosponsor.bioguide_id == member.bioguide_id for cosponsor in bill.cosponsors)
    ]
    related = sponsored + cosponsored
    actions = [action for bill in related for action in bill.actions]

    return MemberProfile(
        **member.model_dump(),
        sponsored_bills=[BillSummary(**bill.model_dump()) for bill in sponsored],
        cosponsored_bills=[BillSummary(**bill.model_dump()) for bill in cosponsored],
        latest_actions=sorted(actions, key=lambda item: item.date or "", reverse=True)[:8],
        committees=[
            Committee(name="Senate Armed Services", chamber="Senate", rank="Member"),
            Committee(name="Senate Veterans' Affairs", chamber="Senate", rank="Member"),
        ]
        if member.bioguide_id == "D000624"
        else [Committee(name="House Homeland Security", chamber="House", rank="Member")],
        bill_status_summaries=[
            f"{bill.bill_type.upper()} {bill.number}: {bill.status or 'Status unavailable'}"
            for bill in related
        ],
    )


ANALYTICS = {
    "most_active_legislators": [
        AnalyticsCard(label="Tammy Duckworth", value=14, detail="Sponsored bills in the selected congress"),
        AnalyticsCard(label="Pramila Jayapal", value=11, detail="Sponsored bills in the selected congress"),
    ],
    "most_bipartisan_bills": [
        AnalyticsCard(label="Cybersecurity Workforce Pipeline Act", value="50/50", detail="Balanced Democratic and Republican cosponsors"),
        AnalyticsCard(label="Education Data Privacy Modernization Act", value="2 parties", detail="Cosponsors from both major parties"),
    ],
    "party_alignment": [
        AnalyticsCard(label="Mike Gallagher", value="82%", detail="Votes with party majority in available House roll calls"),
        AnalyticsCard(label="Pramila Jayapal", value="76%", detail="Votes with party majority in available House roll calls"),
    ],
    "topic_bills": [
        AnalyticsCard(label="Veterans", value=1, detail="Bills tagged veterans"),
        AnalyticsCard(label="Cybersecurity", value=1, detail="Bills tagged cybersecurity"),
        AnalyticsCard(label="Education", value=1, detail="Bills tagged education"),
    ],
    "issue_focus_profiles": [
        AnalyticsCard(label="Tammy Duckworth", value="Veterans, Defense", detail="Based on sponsored and cosponsored bill topics"),
        AnalyticsCard(label="Mike Gallagher", value="Cybersecurity, Defense", detail="Based on sponsored and cosponsored bill topics"),
    ],
}
