import React from "react";
import { createRoot } from "react-dom/client";
import { Activity, BarChart3, Building2, FileText, Search, ShieldAlert, Vote } from "lucide-react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import {
  getAnalytics,
  getBillDetail,
  getHouseVotes,
  getMemberProfile,
  searchMembers,
} from "./api";
import type { AnalyticsResponse, BillDetail, BillSummary, MemberProfile, MemberSummary, VoteExplorerResponse } from "./types";
import "./styles.css";

const chamberOptions = ["", "House", "Senate"];
const partyOptions = ["", "Democratic", "Republican", "Independent"];
const topicFilters = ["Defense", "Veterans", "Cybersecurity", "Education", "Healthcare", "Immigration"];

function App() {
  const [query, setQuery] = React.useState("");
  const [state, setState] = React.useState("");
  const [party, setParty] = React.useState("");
  const [chamber, setChamber] = React.useState("");
  const [topic, setTopic] = React.useState("");
  const [members, setMembers] = React.useState<MemberSummary[]>([]);
  const [selectedMember, setSelectedMember] = React.useState<MemberProfile | null>(null);
  const [selectedBill, setSelectedBill] = React.useState<BillDetail | null>(null);
  const [votes, setVotes] = React.useState<VoteExplorerResponse | null>(null);
  const [analytics, setAnalytics] = React.useState<AnalyticsResponse | null>(null);
  const [status, setStatus] = React.useState("Ready");

  React.useEffect(() => {
    void runSearch();
    void getHouseVotes().then(setVotes).catch(() => setVotes(null));
    void getAnalytics().then(setAnalytics).catch(() => setAnalytics(null));
  }, []);

  async function runSearch(event?: React.FormEvent) {
    event?.preventDefault();
    setStatus("Searching members");
    try {
      const results = await searchMembers({ query, state, party, chamber });
      setMembers(results);
      if (!selectedMember && results[0]) {
        await openMember(results[0].bioguide_id);
      }
      setStatus(`${results.length} members found`);
    } catch {
      setStatus("Backend unavailable");
    }
  }

  async function openMember(bioguideId: string) {
    setStatus("Loading profile");
    const profile = await getMemberProfile(bioguideId);
    setSelectedMember(profile);
    const firstBill = [...profile.sponsored_bills, ...profile.cosponsored_bills][0];
    if (firstBill) {
      await openBill(firstBill.id);
    }
    setStatus("Profile loaded");
  }

  async function openBill(billId: string) {
    setSelectedBill(await getBillDetail(billId));
  }

  const filteredBills = React.useMemo(() => {
    const bills = [...(selectedMember?.sponsored_bills ?? []), ...(selectedMember?.cosponsored_bills ?? [])];
    if (!topic) return bills;
    return bills.filter((bill) => bill.policy_area?.toLowerCase().includes(topic.toLowerCase()));
  }, [selectedMember, topic]);

  return (
    <main className="app-shell">
      <section className="topbar">
        <div>
          <p className="eyebrow">CALID</p>
          <h1>Congressional Activity Intelligence</h1>
        </div>
        <div className="status-pill">{status}</div>
      </section>

      <section className="workspace-grid">
        <aside className="search-panel">
          <form onSubmit={runSearch} className="search-form">
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
                onClick={() => void openMember(member.bioguide_id)}
              >
                {member.image_url ? <img src={member.image_url} alt="" /> : <div className="avatar-fallback">{member.name.slice(0, 1)}</div>}
                <span>
                  <strong>{member.name}</strong>
                  <small>
                    {member.party} · {member.state}
                    {member.district ? `-${member.district}` : ""} · {member.chamber}
                  </small>
                </span>
              </button>
            ))}
          </div>
        </aside>

        <section className="main-stack">
          {selectedMember && (
            <section className="profile-header">
              <div>
                <p className="eyebrow">{selectedMember.chamber}</p>
                <h2>{selectedMember.name}</h2>
                <p>
                  {selectedMember.party} · {selectedMember.state}
                  {selectedMember.district ? `-${selectedMember.district}` : ""}
                </p>
              </div>
              <div className="metric-strip">
                <Metric icon={<FileText size={18} />} label="Sponsored" value={selectedMember.sponsored_bills.length} />
                <Metric icon={<Activity size={18} />} label="Cosponsored" value={selectedMember.cosponsored_bills.length} />
                <Metric icon={<Building2 size={18} />} label="Committees" value={selectedMember.committees.length} />
              </div>
            </section>
          )}

          <section className="content-grid">
            <Panel title="Legislation" icon={<FileText size={18} />}>
              <div className="topic-tabs">
                <button className={!topic ? "selected" : ""} onClick={() => setTopic("")}>
                  All
                </button>
                {topicFilters.map((filter) => (
                  <button key={filter} className={topic === filter ? "selected" : ""} onClick={() => setTopic(filter)}>
                    {filter}
                  </button>
                ))}
              </div>
              <div className="bill-list">
                {filteredBills.map((bill) => (
                  <BillRow key={bill.id} bill={bill} active={selectedBill?.id === bill.id} onSelect={() => void openBill(bill.id)} />
                ))}
              </div>
            </Panel>

            <Panel title="Bill Detail" icon={<ShieldAlert size={18} />}>
              {selectedBill ? (
                <BillDetailView bill={selectedBill} />
              ) : (
                <p className="muted">Select a bill to inspect sponsors, timeline, committees, and status.</p>
              )}
            </Panel>
          </section>

          <section className="content-grid">
            <Panel title="Recent Actions" icon={<Activity size={18} />}>
              <Timeline actions={selectedMember?.latest_actions ?? []} />
            </Panel>
            <Panel title="Committees" icon={<Building2 size={18} />}>
              <div className="committee-list">
                {(selectedMember?.committees ?? []).map((committee) => (
                  <div key={committee.name} className="committee-item">
                    <strong>{committee.name}</strong>
                    <span>
                      {committee.chamber}
                      {committee.rank ? ` · ${committee.rank}` : ""}
                    </span>
                  </div>
                ))}
              </div>
            </Panel>
          </section>

          <section className="content-grid">
            <Panel title="Vote Explorer" icon={<Vote size={18} />}>
              <p className="note">{votes?.note}</p>
              <div className="vote-list">
                {(votes?.votes ?? []).map((vote) => (
                  <div key={`${vote.congress}-${vote.roll_call_number}`} className="vote-item">
                    <strong>
                      Roll {vote.roll_call_number}: {vote.question}
                    </strong>
                    <span>
                      {vote.date} · {vote.result || "Result unavailable"}
                      {vote.member_position ? ` · Member: ${vote.member_position}` : ""}
                    </span>
                  </div>
                ))}
              </div>
            </Panel>

            <Panel title="Analytics" icon={<BarChart3 size={18} />}>
              {analytics && <AnalyticsView analytics={analytics} />}
            </Panel>
          </section>
        </section>
      </section>
    </main>
  );
}

function Metric({ icon, label, value }: { icon: React.ReactNode; label: string; value: number }) {
  return (
    <div className="metric">
      {icon}
      <span>
        <strong>{value}</strong>
        <small>{label}</small>
      </span>
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

function BillRow({ bill, active, onSelect }: { bill: BillSummary; active: boolean; onSelect: () => void }) {
  return (
    <button className={`bill-row ${active ? "active" : ""}`} onClick={onSelect}>
      <span className="bill-code">
        {bill.bill_type.toUpperCase()} {bill.number}
      </span>
      <strong>{bill.title}</strong>
      <small>
        {bill.policy_area || "Policy area unavailable"} · {bill.status || bill.latest_action || "Status unavailable"}
      </small>
    </button>
  );
}

function BillDetailView({ bill }: { bill: BillDetail }) {
  return (
    <div className="bill-detail">
      <div>
        <span className="bill-code">
          {bill.bill_type.toUpperCase()} {bill.number}
        </span>
        <h4>{bill.title}</h4>
        <p>{bill.summary || "No summary is available from the current data source."}</p>
      </div>
      <dl>
        <dt>Sponsor</dt>
        <dd>{bill.sponsor?.name || "Unavailable"}</dd>
        <dt>Latest status</dt>
        <dd>{bill.status || bill.latest_action || "Unavailable"}</dd>
        <dt>Cosponsors</dt>
        <dd>{bill.cosponsors.length ? bill.cosponsors.map((item) => item.name).join(", ") : "None listed"}</dd>
        <dt>Committees</dt>
        <dd>{bill.committees.length ? bill.committees.map((item) => item.name).join(", ") : "None listed"}</dd>
      </dl>
      <Timeline actions={bill.actions} compact />
    </div>
  );
}

function Timeline({ actions, compact = false }: { actions: { date?: string | null; text: string }[]; compact?: boolean }) {
  if (!actions.length) return <p className="muted">No recent actions available.</p>;
  return (
    <ol className={`timeline ${compact ? "compact" : ""}`}>
      {actions.map((action, index) => (
        <li key={`${action.date}-${index}`}>
          <time>{action.date || "Date unavailable"}</time>
          <span>{action.text}</span>
        </li>
      ))}
    </ol>
  );
}

function AnalyticsView({ analytics }: { analytics: AnalyticsResponse }) {
  const chartData = analytics.topic_bills.map((item) => ({ name: item.label, bills: Number(item.value) || 0 }));

  return (
    <div className="analytics-stack">
      <div className="chart-wrap">
        <ResponsiveContainer width="100%" height={180}>
          <BarChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="name" />
            <YAxis allowDecimals={false} />
            <Tooltip />
            <Bar dataKey="bills" fill="#2f6f73" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="analytics-list">
        {analytics.most_active_legislators.slice(0, 2).map((item) => (
          <div key={item.label}>
            <strong>{item.label}</strong>
            <span>
              {item.value} · {item.detail}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
