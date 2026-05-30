export type MemberSummary = {
  bioguide_id: string;
  name: string;
  state: string;
  party: string;
  chamber: string;
  district?: string | null;
  image_url?: string | null;
};

export type Action = {
  date?: string | null;
  text: string;
  action_type?: string | null;
};

export type Committee = {
  name: string;
  chamber?: string | null;
  rank?: string | null;
};

export type BillSummary = {
  id: string;
  congress: number;
  bill_type: string;
  number: string;
  title: string;
  latest_action?: string | null;
  latest_action_date?: string | null;
  policy_area?: string | null;
  status?: string | null;
};

export type Cosponsor = {
  bioguide_id?: string | null;
  name: string;
  party?: string | null;
  state?: string | null;
  date?: string | null;
  is_original_cosponsor?: boolean | null;
};

export type BillDetail = BillSummary & {
  sponsor?: MemberSummary | null;
  cosponsors: Cosponsor[];
  summary?: string | null;
  actions: Action[];
  committees: Committee[];
};

export type MemberProfile = MemberSummary & {
  sponsored_bills: BillSummary[];
  cosponsored_bills: BillSummary[];
  latest_actions: Action[];
  committees: Committee[];
  bill_status_summaries: string[];
};

export type Vote = {
  congress: number;
  session: number;
  chamber: string;
  roll_call_number: number;
  date?: string | null;
  question: string;
  result?: string | null;
  bill_id?: string | null;
  member_position?: string | null;
  source_url?: string | null;
};

export type VoteExplorerResponse = {
  votes: Vote[];
  note: string;
};

export type AnalyticsCard = {
  label: string;
  value: string | number;
  detail?: string | null;
};

export type AnalyticsResponse = {
  most_active_legislators: AnalyticsCard[];
  most_bipartisan_bills: AnalyticsCard[];
  party_alignment: AnalyticsCard[];
  topic_bills: AnalyticsCard[];
  issue_focus_profiles: AnalyticsCard[];
};
