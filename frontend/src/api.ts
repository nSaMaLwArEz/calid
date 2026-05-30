import type {
  AnalyticsResponse,
  BillDetail,
  BillSummary,
  MemberProfile,
  MemberSummary,
  MemberVotingProfile,
  PaginatedResponse,
  VoteBillListResponse,
  VoteExplorerResponse,
  VoteMemberListResponse,
} from "./types";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? (typeof window !== "undefined" ? window.location.origin : "http://localhost:8000");

async function request<T>(path: string, params?: Record<string, string | number | undefined>): Promise<T> {
  const url = new URL(path, API_BASE_URL);
  Object.entries(params ?? {}).forEach(([key, value]) => {
    if (value !== undefined && value !== "") {
      url.searchParams.set(key, String(value));
    }
  });

  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function searchMembers(params: {
  query?: string;
  state?: string;
  party?: string;
  chamber?: string;
  limit?: number;
  offset?: number;
}): Promise<PaginatedResponse<MemberSummary>> {
  return request<PaginatedResponse<MemberSummary>>("/members", params);
}

export function getBills(params: {
  congress?: number;
  bill_type?: string;
  limit?: number;
  offset?: number;
}): Promise<PaginatedResponse<BillSummary>> {
  return request<PaginatedResponse<BillSummary>>("/bills", params);
}

export function getMemberProfile(bioguideId: string): Promise<MemberProfile> {
  return request<MemberProfile>(`/members/${bioguideId}`);
}

export function getMemberVotingProfile(bioguideId: string, congress = 119, session = 1): Promise<MemberVotingProfile> {
  return request<MemberVotingProfile>(`/members/${bioguideId}/voting`, { congress, session });
}

export function getBillDetail(billId: string): Promise<BillDetail> {
  return request<BillDetail>(`/bills/${billId}`);
}

export function getHouseVotes(congress = 119, session = 1): Promise<VoteExplorerResponse> {
  return request<VoteExplorerResponse>("/votes/house", { congress, session });
}

export function getVoteBills(params: { congress?: number; session?: number; limit?: number; offset?: number }): Promise<VoteBillListResponse> {
  return request<VoteBillListResponse>("/vote-bills", params);
}

export function getVoteMembers(congress: number, session: number, rollCallNumber: number): Promise<VoteMemberListResponse> {
  return request<VoteMemberListResponse>(`/votes/house/${congress}/${session}/${rollCallNumber}/members`);
}

export function getAnalytics(): Promise<AnalyticsResponse> {
  return request<AnalyticsResponse>("/analytics");
}
