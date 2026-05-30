import React from "react";
import { createRoot } from "react-dom/client";
import { BarChart3, FileText, Search, UserRound, Vote } from "lucide-react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import {
  getBillDetail,
  getMemberProfile,
  getMemberVotingProfile,
  getVoteBills,
  getVoteMembers,
  searchMembers,
} from "./api";
import type {
  BillDetail,
  BillSummary,
  MemberProfile,
  MemberSummary,
  MemberVotingProfile,
  VoteBillListResponse,
  VoteBillSummary,
  VoteMemberListResponse,
} from "./types";
import "./styles.css";

const pageSize = 50;
const votePageSize = 10;
const chamberOptions = ["", "House", "Senate"];
const partyOptions = ["", "Democratic", "Republican", "Independent"];

function App() {
  const [page, setPage] = React.useState<"members" | "bills">("members");
  const [query, setQuery] = React.useState("");
  const [state, setState] = React.useState("");
  const [party, setParty] = React.useState("");
  const [chamber, setChamber] = React.useState("");
  const [memberOffset, setMemberOffset] = React.useState(0);
  const [members, setMembers] = React.useState<MemberSummary[]>([]);
  const [memberTotal, setMemberTotal] = React.useState<number | null>(null);
  const [selectedMember, setSelectedMember] = React.useState<MemberProfile | null>(null);
  const [memberVotes, setMemberVotes] = React.useState<MemberVotingProfile | null>(null);
  const [selectedBill, setSelectedBill] = React.useState<BillDetail | null>(null);
  const [voteBills, setVoteBills] = React.useState<VoteBillListResponse | null>(null);
  const [voteOffset, setVoteOffset] = React.useState(0);
  const [selectedVoteRoster, setSelectedVoteRoster] = React.useState<VoteMemberListResponse | null>(null);
  const [status, setStatus] = React.useState("Ready");

  React.useEffect(() => {
    void loadMembers(0);
    void loadVoteBills(0);
  }, []);

  async function loadMembers(offset: number) {
    setStatus("Loading members");
    try {
      const response = await searchMembers({ query, state, party, chamber, limit: pageSize, offset });
      setMembers(response.items);
      setMemberOffset(response.offset);
      setMemberTotal(response.total ?? null);
      if (!selectedMember && response.items[0]) {
        await openMember(response.items[0].bioguide_id);
      }
      setStatus(`${response.items.length} members loaded`);
    } catch {
      setStatus("Member data failed. Check /diagnostics/congress");
    }
  }

  async function openMember(bioguideId: string) {
    setPage("members");
    setStatus("Loading profile");
    const [profile, voting] = await Promise.all([getMemberProfile(bioguideId), getMemberVotingProfile(bioguideId)]);
    setSelectedMember(profile);
    setMemberVotes(voting);
    const firstBill = [...profile.sponsored_bills, ...profile.cosponsored_bills][0];
    if (firstBill) {
      await openBill(firstBill.id, false);
    }
    setStatus("Profile loaded");
  }

  async function openBill(billId: string, switchPage = true) {
    setSelectedBill(await getBillDetail(billId));
    if (switchPage) {
      setPage("bills");
    }
  }

  async function loadVoteBills(offset: number) {
    setStatus("Loading vote bills");
    try {
      const response = await getVoteBills({ congress: 119, session: 1, limit: votePageSize, offset });
      setVoteBills(response);
      setVoteOffset(response.offset);
      setStatus(`${response.items.length} vote records loaded`);
    } catch {
      setStatus("Vote data unavailable");
    }
  }

  async function openVoteRoster(vote: VoteBillSummary) {
    setStatus("Loading vote roster");
    setSelectedVoteRoster(await getVoteMembers(vote.congress, vote.session, vote.roll_call_number));
    setStatus("Vote roster loaded");
  }

  return (
    <main className="app-shell">
      <nav className="topnav">
        <div>
          <p className="eyebrow">CALID</p>
          <h1>Congressional Activity Intelligence</h1>
        </div>
        <div className="nav-actions">
          <button className={page === "members" ? "selected" : ""} onClick={() => setPage("members")}>
            <UserRound size={17} />
            Congressperson
          </button>
          <button className={page === "bills" ? "selected" : ""} onClick={() => setPage("bills")}>
            <FileText size={17} />
            Bills
          </button>
          <span className="status-pill">{status}</span>
        </div>
      </nav>

      {page === "members" ? (
        <CongresspersonPage
          query={query}
          setQuery={setQuery}
          state={state}
          setState={setState}
          party={party}
          setParty={setParty}
          chamber={chamber}
          setChamber={setChamber}
          members={members}
          memberOffset={memberOffset}
          memberTotal={memberTotal}
          selectedMember={selectedMember}
          memberVotes={memberVotes}
          selectedBill={selectedBill}
          onSearch={() => void loadMembers(0)}
          onPageMembers={loadMembers}
          onOpenMember={openMember}
          onOpenBill={(billId) => void openBill(billId)}
        />
      ) : (
        <BillsPage
          voteBills={voteBills}
          voteOffset={voteOffset}
          selectedVoteRoster={selectedVoteRoster}
          selectedBill={selectedBill}
          onPageVotes={loadVoteBills}
          onOpenRoster={openVoteRoster}
          onOpenBill={(billId) => void openBill(billId, false)}
        />
      )}
    </main>
  );
}

function CongresspersonPage({
  query,
  setQuery,
  state,
  setState,
  party,
  setParty,
  chamber,
  setChamber,
  members,
  memberOffset,
  memberTotal,
  selectedMember,
  memberVotes,
  selectedBill,
  onSearch,
  onPageMembers,
  onOpenMember,
  onOpenBill,
}: {
  query: string;
  setQuery: (value: string) => void;
  state: string;
  setState: (value: string) => void;
  party: string;
  setParty: (value: string) => void;
  chamber: string;
  setChamber: (value: string) => void;
  members: MemberSummary[];
  memberOffset: number;
  memberTotal: number | null;
  selectedMember: MemberProfile | null;
  memberVotes: MemberVotingProfile | null;
  selectedBill: BillDetail | null;
  onSearch: () => void;
  onPageMembers: (offset: number) => void;
  onOpenMember: (bioguideId: string) => void;
  onOpenBill: (billId: string) => void;
}) {
  const compactBills = [...(selectedMember?.sponsored_bills ?? []), ...(selectedMember?.cosponsored_bills ?? [])].slice(0, 12);

  return (
    <section className="page-grid">
      <aside className="sidebar">
        <form
          className="search-form"
          onSubmit={(event) => {
            event.preventDefault();
            onSearch();
          }}
        >
          <label>
            Name
            <div className="input-icon">
              <Search size={16} />
              <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search a member" />
            </div>
          </label>
          <div className="field-row">
            <label>
              State
              <input value={state} maxLength={2} onChange={(event) => setState(event.target.value.toUpperCase())} placeholder="IL" />
            </label>
            <label>
              Chamber
              <select value={chamber} onChange={(event) => setChamber(event.target.value)}>
                {chamberOptions.map((option) => (
                  <option key={option} value={option}>
                    {option || "Any"}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <label>
            Party
            <select value={party} onChange={(event) => setParty(event.target.value)}>
              {partyOptions.map((option) => (
                <option key={option} value={option}>
                  {option || "Any"}
                </option>
              ))}
            </select>
          </label>
          <button className="primary-button" type="submit">
            <Search size={16} />
            Search
          </button>
        </form>

        <div className="member-list">
          {members.map((member) => (
            <button
              key={member.bioguide_id}
              className={`member-result ${selectedMember?.bioguide_id === member.bioguide_id ? "active" : ""}`}
              onClick={() => onOpenMember(member.bioguide_id)}
            >
              {member.image_url ? <img src={member.image_url} alt="" /> : <div className="avatar-fallback">{member.name.slice(0, 1)}</div>}
              <span>
                <strong>{member.name}</strong>
                <small>
                  {member.party} - {member.state}
                  {member.district ? `-${member.district}` : ""} - {member.chamber}
                </small>
              </span>
            </button>
          ))}
        </div>
        <PaginationControls
          offset={memberOffset}
          limit={pageSize}
          total={memberTotal}
          label="members"
          onPrevious={() => onPageMembers(Math.max(0, memberOffset - pageSize))}
          onNext={() => onPageMembers(memberOffset + pageSize)}
        />
      </aside>

      <section className="detail-stack">
        {selectedMember && (
          <section className="profile-header">
            <div>
              <p className="eyebrow">{selectedMember.chamber}</p>
              <h2>{selectedMember.name}</h2>
              <p>
                {selectedMember.party} - {selectedMember.state}
                {selectedMember.district ? `-${selectedMember.district}` : ""}
              </p>
            </div>
            <div className="metric-strip">
              <Metric label="Participated" value={memberVotes?.participated ?? 0} />
              <Metric label="Missed" value={memberVotes?.missed ?? 0} />
              <Metric label="Scanned Votes" value={memberVotes?.scanned_votes ?? 0} />
            </div>
          </section>
        )}

        <section className="content-grid">
          <Panel title="Voting By Month" icon={<BarChart3 size={18} />}>
            {memberVotes && (
              <p className="note">
                Showing {memberVotes.scanned_votes}
                {memberVotes.available_votes ? ` of ${memberVotes.available_votes}` : ""} available House roll-call votes.
              </p>
            )}
            {memberVotes?.monthly.length ? (
              <div className="chart-wrap tall">
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart data={memberVotes.monthly}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="month" />
                    <YAxis allowDecimals={false} />
                    <Tooltip />
                    <Legend />
                    <Bar dataKey="participated" stackId="votes" fill="#2f6f73" />
                    <Bar dataKey="missed" stackId="votes" fill="#b65f3a" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <p className="muted">{memberVotes?.note || "Select a member to see voting activity."}</p>
            )}
          </Panel>

          <Panel title="Compact Bill Links" icon={<FileText size={18} />}>
            <div className="compact-bill-list">
              {compactBills.map((bill) => (
                <button key={bill.id} onClick={() => onOpenBill(bill.id)}>
                  <span>{bill.bill_type.toUpperCase()} {bill.number}</span>
                  <strong>{bill.title}</strong>
                </button>
              ))}
            </div>
          </Panel>
        </section>

        <section className="content-grid">
          <Panel title="Bills Voted For Or Against" icon={<Vote size={18} />}>
            <div className="vote-history-list">
              {(memberVotes?.votes ?? []).map((vote) => (
                <button key={`${vote.congress}-${vote.session}-${vote.roll_call_number}`} onClick={() => vote.bill_id && onOpenBill(vote.bill_id)}>
                  <strong>{vote.question}</strong>
                  <span>
                    Roll {vote.roll_call_number} - {vote.date || "Date unavailable"} - {vote.member_position || "Unavailable"}
                  </span>
                </button>
              ))}
            </div>
          </Panel>

          <Panel title="Selected Bill" icon={<FileText size={18} />}>
            {selectedBill ? <BillDetailView bill={selectedBill} /> : <p className="muted">Select a linked bill to view details.</p>}
          </Panel>
        </section>
      </section>
    </section>
  );
}

function BillsPage({
  voteBills,
  voteOffset,
  selectedVoteRoster,
  selectedBill,
  onPageVotes,
  onOpenRoster,
  onOpenBill,
}: {
  voteBills: VoteBillListResponse | null;
  voteOffset: number;
  selectedVoteRoster: VoteMemberListResponse | null;
  selectedBill: BillDetail | null;
  onPageVotes: (offset: number) => void;
  onOpenRoster: (vote: VoteBillSummary) => void;
  onOpenBill: (billId: string) => void;
}) {
  return (
    <section className="detail-stack full">
      <section className="content-grid wide-left">
        <Panel title="Bills And Vote Counts" icon={<Vote size={18} />}>
          <p className="note">{voteBills?.note || "Loading vote-backed bill records."}</p>
          <div className="vote-bill-list">
            {(voteBills?.items ?? []).map((vote) => (
              <div key={`${vote.congress}-${vote.session}-${vote.roll_call_number}`} className="vote-bill-row">
                <button className="vote-title" onClick={() => vote.bill_id && onOpenBill(vote.bill_id)}>
                  <strong>{vote.question}</strong>
                  <span>
                    Roll {vote.roll_call_number} - {vote.date || "Date unavailable"} - {vote.result || "Result unavailable"}
                  </span>
                </button>
                <button className="vote-count" onClick={() => onOpenRoster(vote)}>
                  <strong>{vote.yea + vote.nay + vote.abstained + vote.not_voting}</strong>
                  <span>votes</span>
                </button>
                <div className="vote-pills">
                  <span>Yea {vote.yea}</span>
                  <span>Nay {vote.nay}</span>
                  <span>Abstain {vote.abstained}</span>
                  <span>Not voting {vote.not_voting}</span>
                </div>
              </div>
            ))}
          </div>
          <PaginationControls
            offset={voteOffset}
            limit={votePageSize}
            total={voteBills?.total ?? null}
            label="vote records"
            onPrevious={() => onPageVotes(Math.max(0, voteOffset - votePageSize))}
            onNext={() => onPageVotes(voteOffset + votePageSize)}
          />
        </Panel>

        <Panel title="Vote Roster" icon={<UserRound size={18} />}>
          {selectedVoteRoster ? (
            <div className="roster-list">
              {selectedVoteRoster.members.map((member, index) => (
                <div key={`${member.bioguide_id || member.name}-${index}`}>
                  <strong>{member.name}</strong>
                  <span>
                    {member.party || "Party unavailable"} - {member.state || "State unavailable"} - {member.vote}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="muted">Click a vote count to view the member roster.</p>
          )}
        </Panel>
      </section>

      <Panel title="Linked Bill Detail" icon={<FileText size={18} />}>
        {selectedBill ? <BillDetailView bill={selectedBill} /> : <p className="muted">Click a bill title to open bill details.</p>}
      </Panel>
    </section>
  );
}

function PaginationControls({
  offset,
  limit,
  total,
  label,
  onPrevious,
  onNext,
}: {
  offset: number;
  limit: number;
  total: number | null;
  label: string;
  onPrevious: () => void;
  onNext: () => void;
}) {
  const end = total === null ? offset + limit : Math.min(offset + limit, total);
  const canGoNext = total === null || offset + limit < total;

  return (
    <div className="pagination-controls">
      <button type="button" onClick={onPrevious} disabled={offset === 0}>
        Previous
      </button>
      <span>
        {offset + 1}-{end}
        {total !== null ? ` of ${total}` : ""} {label}
      </span>
      <button type="button" onClick={onNext} disabled={!canGoNext}>
        Next
      </button>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="metric">
      <strong>{value}</strong>
      <small>{label}</small>
    </div>
  );
}

function Panel({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="panel">
      <header>
        <span>{icon}</span>
        <h3>{title}</h3>
      </header>
      {children}
    </section>
  );
}

function BillDetailView({ bill }: { bill: BillDetail }) {
  return (
    <div className="bill-detail">
      <span className="bill-code">
        {bill.bill_type.toUpperCase()} {bill.number}
      </span>
      <h4>{bill.title}</h4>
      <p>{bill.summary || bill.latest_action || "No summary is available from the current data source."}</p>
      <dl>
        <dt>Sponsor</dt>
        <dd>{bill.sponsor?.name || "Unavailable"}</dd>
        <dt>Status</dt>
        <dd>{bill.status || bill.latest_action || "Unavailable"}</dd>
        <dt>Committees</dt>
        <dd>{bill.committees.length ? bill.committees.map((item) => item.name).join(", ") : "None listed"}</dd>
      </dl>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
