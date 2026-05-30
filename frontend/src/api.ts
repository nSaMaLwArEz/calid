import type { AnalyticsResponse, BillDetail, MemberProfile, MemberSummary, VoteExplorerResponse } from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

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
}): Promise<MemberSummary[]> {
  return request<MemberSummary[]>("/members", params);
}

export function getMemberProfile(bioguideId: string): Promise<MemberProfile> {
  return request<MemberProfile>(`/members/${bioguideId}`);
}

export function getBillDetail(billId: string): Promise<BillDetail> {
  return request<BillDetail>(`/bills/${billId}`);
}

export function getHouseVotes(congress = 119, session = 1): Promise<VoteExplorerResponse> {
  return request<VoteExplorerResponse>("/votes/house", { congress, session });
}

export function getAnalytics(): Promise<AnalyticsResponse> {
  return request<AnalyticsResponse>("/analytics");
}
