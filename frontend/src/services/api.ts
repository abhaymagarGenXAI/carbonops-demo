/**
 * Centralised HTTP client for the FastAPI backend.
 *
 *  - base URL from VITE_API_BASE_URL (defaults to "/api/v1", proxied by Vite in dev)
 *  - request interceptor: injects the JWT access token
 *  - response interceptor: on 401 transparently refreshes the token (single-flight) and replays
 *    the request once; if refresh fails the session is cleared and the app is sent to /login
 *  - every failure is normalised into an `ApiError` whose `.message` is human-readable, so
 *    existing `error instanceof Error ? error.message : …` toast code keeps working
 *
 * Token storage: the short-lived ACCESS token lives only in memory (never localStorage ⇒ not
 * readable by injected scripts after a reload). The long-lived REFRESH token is an httpOnly
 * cookie set by FastAPI that JavaScript cannot see; it is sent only to /auth/*.
 */
import axios, { AxiosError, type AxiosResponse, type InternalAxiosRequestConfig } from "axios";
import type { UserRec } from "@/types/domain";

export const API_BASE_URL: string =
  ((import.meta.env["VITE_API_BASE_URL"] as string | undefined) ?? "").replace(/\/$/, "") || "/api/v1";

export interface TokenResponse {
  accessToken: string;
  tokenType: "bearer";
  expiresIn: number;
  user: UserRec;
}

/* ----------------------------------------------------------------- errors */

export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(message: string, status: number, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

function messageFromBody(data: unknown, fallback: string): string {
  if (data && typeof data === "object" && "detail" in data) {
    const detail = (data as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      // FastAPI/Pydantic validation errors: [{ loc: ["body","field"], msg: "..." }]
      return detail
        .map((e: { loc?: unknown[]; msg?: string }) => {
          const where = (e.loc ?? []).filter((p) => p !== "body" && p !== "query").join(".");
          return where ? `${where}: ${e.msg ?? "invalid"}` : (e.msg ?? "invalid");
        })
        .join("; ");
    }
  }
  return fallback;
}

export function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;
  if (axios.isAxiosError(error)) {
    if (!error.response) {
      return new ApiError("Cannot reach the server. Check your connection and try again.", 0);
    }
    const { status, data } = error.response;
    return new ApiError(messageFromBody(data, `Request failed (${status})`), status, data);
  }
  return new ApiError(error instanceof Error ? error.message : "Unexpected error", 0);
}

/* ------------------------------------------------------------ token state */

let accessToken: string | null = null;
export const getAccessToken = () => accessToken;
export const setAccessToken = (token: string | null) => {
  accessToken = token;
};

let onAuthFailure: (() => void) | null = null;
/** AuthProvider registers a callback so a failed refresh can reset React state + redirect. */
export const registerAuthFailureHandler = (fn: (() => void) | null) => {
  onAuthFailure = fn;
};

/* ---------------------------------------------------------------- clients */

const baseConfig = { baseURL: API_BASE_URL, withCredentials: true, timeout: 20_000 } as const;

/** Main client (with interceptors). */
export const api = axios.create({ ...baseConfig, headers: { "Content-Type": "application/json" } });

/** Interceptor-free client used for /auth/* to avoid refresh recursion. */
const bare = axios.create({ ...baseConfig, headers: { "Content-Type": "application/json" } });

const AUTH_PATHS = ["/auth/login", "/auth/refresh", "/auth/logout"];
const isAuthPath = (url?: string) => !!url && AUTH_PATHS.some((p) => url.includes(p));

type Retriable = InternalAxiosRequestConfig & { _retried?: boolean };

api.interceptors.request.use((config) => {
  const token = getAccessToken();
  if (token) config.headers.set("Authorization", `Bearer ${token}`);
  return config;
});

let refreshInFlight: Promise<TokenResponse> | null = null;

/** Exchange the refresh cookie for a new access token. Concurrent callers share one request. */
export function refreshSession(): Promise<TokenResponse> {
  if (!refreshInFlight) {
    refreshInFlight = bare
      .post<TokenResponse>("/auth/refresh")
      .then((res) => {
        setAccessToken(res.data.accessToken);
        return res.data;
      })
      .finally(() => {
        refreshInFlight = null;
      });
  }
  return refreshInFlight;
}

api.interceptors.response.use(
  (response: AxiosResponse) => response,
  async (error: AxiosError) => {
    const original = error.config as Retriable | undefined;

    if (error.response?.status === 401 && original && !original._retried && !isAuthPath(original.url)) {
      original._retried = true;
      try {
        const session = await refreshSession();
        original.headers.set("Authorization", `Bearer ${session.accessToken}`);
        return await api.request(original);
      } catch {
        setAccessToken(null);
        onAuthFailure?.();
        return Promise.reject(new ApiError("Your session has expired. Please sign in again.", 401));
      }
    }
    return Promise.reject(toApiError(error));
  },
);

/* ------------------------------------------------------------- auth calls */

export const authApi = {
  async login(email: string, password: string): Promise<TokenResponse> {
    try {
      const res = await bare.post<TokenResponse>("/auth/login", { email, password });
      setAccessToken(res.data.accessToken);
      return res.data;
    } catch (e) {
      throw toApiError(e);
    }
  },

  /** Restore a session on page load using the httpOnly refresh cookie. */
  async restore(): Promise<TokenResponse | null> {
    try {
      return await refreshSession();
    } catch {
      setAccessToken(null);
      return null;
    }
  },

  async logout(): Promise<void> {
    try {
      await bare.post("/auth/logout");
    } catch {
      /* best effort: the local session is cleared regardless */
    } finally {
      setAccessToken(null);
    }
  },
};
