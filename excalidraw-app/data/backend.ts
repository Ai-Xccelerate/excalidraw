import { clearAppStateForDatabase } from "@excalidraw/excalidraw/appState";

import type { OrderedExcalidrawElement } from "@excalidraw/element/types";
import type { AppState, BinaryFiles } from "@excalidraw/excalidraw/types";

import { atom } from "../app-jotai";

import type { Socket } from "socket.io-client";

import type { SyncableExcalidrawElement } from ".";

const API_URL = import.meta.env.VITE_APP_API_URL as string;

const TOKEN_KEY = "aixdraw-auth-token";
const WORKSPACE_KEY = "aixdraw-active-workspace";

/** the drawing currently open in the editor when not collaborating, if any;
 * used by App.tsx's onChange to autosave to the backend instead of/alongside
 * localStorage once a signed-in user has a drawing open */
export const currentDrawingIdAtom = atom<string | null>(null);

export type AuthUser = {
  id: string;
  email: string;
  username: string | null;
  avatar_url: string | null;
  email_verified: boolean;
};

export type Session = { token: string; user: AuthUser };

export type SignupResult = { ok: boolean; message: string };

export const getStoredToken = (): string | null => {
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
};

export const setStoredToken = (token: string): void => {
  try {
    window.localStorage.setItem(TOKEN_KEY, token);
  } catch {
    // private-mode storage failure: the session just won't survive a reload
  }
};

/** Fires when the server rejects the stored token. AuthContext listens so the
 * in-memory user is dropped too — clearing storage alone left the app rendering
 * as signed-in until the next reload. */
export const SESSION_EXPIRED_EVENT = "aixdraw:session-expired";

export const clearStoredToken = (): void => {
  try {
    window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    // nothing to do
  }
};

export const getActiveWorkspaceId = (): string | null => {
  try {
    return window.localStorage.getItem(WORKSPACE_KEY);
  } catch {
    return null;
  }
};

export const setActiveWorkspaceId = (id: string | null): void => {
  try {
    if (id) {
      window.localStorage.setItem(WORKSPACE_KEY, id);
    } else {
      window.localStorage.removeItem(WORKSPACE_KEY);
    }
  } catch {
    // nothing to do
  }
};

/** The token is read synchronously from localStorage, so unlike the old Clerk
 * flow there is nothing to wait for before the first request goes out. */
export const getAuthToken = async (): Promise<string | null> =>
  getStoredToken();

const apiFetch = async (path: string, init: RequestInit = {}) => {
  const token = getStoredToken();
  const workspaceId = getActiveWorkspaceId();
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(workspaceId ? { "X-Workspace-Id": workspaceId } : {}),
      ...init.headers,
    },
  });
  if (!response.ok) {
    const body = await response.text();
    // a rejected token is dead for every future request; drop it so the app
    // falls back to the sign-in screen instead of retrying with it forever
    if (response.status === 401 && token) {
      clearStoredToken();
      window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
    }
    let message = `API ${path} failed (${response.status})`;
    try {
      const detail = JSON.parse(body)?.detail;
      if (typeof detail === "string") {
        message = detail;
      }
    } catch {
      // non-JSON error body; keep the generic message
    }
    throw new Error(message);
  }
  if (response.status === 204) {
    return null;
  }
  return response.json();
};

/** Deliberately returns no session: the account can't be trusted with anything
 * addressed to that email until the address is verified, and answering
 * differently for a taken address would leak which emails have accounts. */
export const signup = (
  email: string,
  password: string,
  username?: string,
): Promise<SignupResult> =>
  apiFetch("/api/auth/signup", {
    method: "POST",
    body: JSON.stringify({ email, password, username }),
  });

export const verifyEmail = (token: string): Promise<Session> =>
  apiFetch("/api/auth/verify-email", {
    method: "POST",
    body: JSON.stringify({ token }),
  });

export const resendVerification = (email: string): Promise<SignupResult> =>
  apiFetch("/api/auth/resend-verification", {
    method: "POST",
    body: JSON.stringify({ email }),
  });

export const login = (email: string, password: string): Promise<Session> =>
  apiFetch("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });

export const getMe = (): Promise<AuthUser> => apiFetch("/api/auth/me");

export const forgotPassword = (email: string): Promise<void> =>
  apiFetch("/api/auth/forgot-password", {
    method: "POST",
    body: JSON.stringify({ email }),
  });

export const resetPassword = (
  token: string,
  password: string,
): Promise<Session> =>
  apiFetch("/api/auth/reset-password", {
    method: "POST",
    body: JSON.stringify({ token, password }),
  });

/** Returns a replacement token: changing the password invalidates every
 * session issued before it, including the one making this call. */
export const changePassword = (
  currentPassword: string,
  newPassword: string,
): Promise<{ ok: boolean; token: string }> =>
  apiFetch("/api/auth/change-password", {
    method: "POST",
    body: JSON.stringify({
      current_password: currentPassword,
      new_password: newPassword,
    }),
  });

export type DrawingSummary = {
  id: string;
  title: string;
  updated_at: string;
  role: "owner" | "editor" | "viewer";
  thumbnail: string | null;
  workspace_id: string | null;
  collection_id: string | null;
};

export type DrawingRecord = {
  id: string;
  title: string;
  elements: OrderedExcalidrawElement[];
  app_state: Partial<AppState>;
  files: BinaryFiles;
  scene_version: number;
  is_room_active: boolean;
  role: "owner" | "editor" | "viewer";
  workspace_id: string | null;
  collection_id: string | null;
};

export type Workspace = {
  id: string;
  name: string;
  role: "admin" | "member";
};

export type WorkspaceMember = {
  user_id: string | null;
  email: string;
  role: "admin" | "member";
  pending: boolean;
};

export type CollectionRecord = {
  id: string;
  name: string;
  workspace_id: string | null;
};

export const listDrawings = (): Promise<DrawingSummary[]> =>
  apiFetch("/api/drawings");

export const createDrawing = (
  title = "Untitled",
  collectionId: string | null = null,
): Promise<DrawingRecord> =>
  apiFetch("/api/drawings", {
    method: "POST",
    body: JSON.stringify({ title, collection_id: collectionId }),
  });

export const getDrawing = (id: string): Promise<DrawingRecord> =>
  apiFetch(`/api/drawings/${id}`);

export const deleteDrawing = (id: string): Promise<void> =>
  apiFetch(`/api/drawings/${id}`, { method: "DELETE" });

export const renameDrawing = (
  id: string,
  title: string,
): Promise<DrawingSummary> =>
  apiFetch(`/api/drawings/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ title }),
  });

export type Member = {
  user_id: string | null;
  email: string;
  role: "owner" | "editor" | "viewer";
  pending: boolean;
};

export const listMembers = (id: string): Promise<Member[]> =>
  apiFetch(`/api/drawings/${id}/members`);

export const inviteMember = (
  id: string,
  email: string,
  role: "editor" | "viewer" = "editor",
): Promise<{ ok: boolean; pending: boolean }> =>
  apiFetch(`/api/drawings/${id}/members`, {
    method: "POST",
    body: JSON.stringify({ email, role }),
  });

export const removeMember = (id: string, userId: string): Promise<void> =>
  apiFetch(`/api/drawings/${id}/members/${userId}`, { method: "DELETE" });

export const removePendingInvite = (id: string, email: string): Promise<void> =>
  apiFetch(`/api/drawings/${id}/pending-invites/${encodeURIComponent(email)}`, {
    method: "DELETE",
  });

export const moveDrawing = (
  id: string,
  collectionId: string | null,
): Promise<DrawingSummary> =>
  apiFetch(`/api/drawings/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ collection_id: collectionId }),
  });

export const listWorkspaces = (): Promise<Workspace[]> =>
  apiFetch("/api/workspaces");

export const createWorkspace = (name: string): Promise<Workspace> =>
  apiFetch("/api/workspaces", {
    method: "POST",
    body: JSON.stringify({ name }),
  });

export const listWorkspaceMembers = (
  workspaceId: string,
): Promise<WorkspaceMember[]> =>
  apiFetch(`/api/workspaces/${workspaceId}/members`);

export const inviteWorkspaceMember = (
  workspaceId: string,
  email: string,
  role: "admin" | "member" = "member",
): Promise<{ ok: boolean; pending: boolean }> =>
  apiFetch(`/api/workspaces/${workspaceId}/members`, {
    method: "POST",
    body: JSON.stringify({ email, role }),
  });

export const removeWorkspaceMember = (
  workspaceId: string,
  userId: string,
): Promise<void> =>
  apiFetch(`/api/workspaces/${workspaceId}/members/${userId}`, {
    method: "DELETE",
  });

export const listCollections = (
  workspaceId: string | null,
): Promise<CollectionRecord[]> =>
  apiFetch(
    workspaceId
      ? `/api/collections?workspace_id=${encodeURIComponent(workspaceId)}`
      : "/api/collections",
  );

export const createCollection = (
  name: string,
  workspaceId: string | null,
): Promise<CollectionRecord> =>
  apiFetch("/api/collections", {
    method: "POST",
    body: JSON.stringify({ name, workspace_id: workspaceId }),
  });

export const renameCollection = (
  id: string,
  name: string,
): Promise<CollectionRecord> =>
  apiFetch(`/api/collections/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ name }),
  });

export const deleteCollection = (id: string): Promise<void> =>
  apiFetch(`/api/collections/${id}`, { method: "DELETE" });

// element-version sum of the last payload we successfully saved, per drawing id,
// mirroring FirebaseSceneVersionCache's purpose of skipping redundant saves.
// NOTE: this deliberately tracks the *local* sum, not the drawing's
// `scene_version` — that column is a server-assigned monotonic counter, so
// comparing it to a sum of element versions would never match and would leave
// every drawing looking permanently unsaved.
const LastSavedElementsVersion = new Map<string, number>();

export const isSavedToBackend = (
  drawingId: string | null,
  elements: readonly SyncableExcalidrawElement[],
): boolean => {
  if (!drawingId) {
    return true;
  }
  const saved = LastSavedElementsVersion.get(drawingId);
  return saved !== undefined && saved === getVersion(elements);
};

const getVersion = (elements: readonly OrderedExcalidrawElement[]) =>
  elements.reduce((total, el) => total + el.version, 0);

export const saveDrawing = async (
  drawingId: string,
  elements: readonly SyncableExcalidrawElement[],
  appState: Partial<AppState>,
  files: BinaryFiles,
  thumbnail?: string | null,
): Promise<DrawingRecord> => {
  const sceneVersion = getVersion(elements);
  const result: DrawingRecord = await apiFetch(`/api/drawings/${drawingId}`, {
    method: "PUT",
    body: JSON.stringify({
      elements,
      // strip volatile/session-only appState (collaborators Map, selection,
      // scroll/zoom, editing refs). Persisting the raw appState serializes
      // `collaborators` to {}, which crashes on reload (.forEach is not a fn).
      app_state: clearAppStateForDatabase(appState),
      files,
      // ignored by the server (it owns scene_version) but still sent so a
      // frontend that rolls ahead of the API keeps working against the old one
      scene_version: sceneVersion,
      // keep the dashboard's drawing.title in sync with the scene name that
      // Excalidraw's built-in "Rename scene" edits (appState.name)
      ...(appState.name ? { title: appState.name } : {}),
      ...(thumbnail ? { thumbnail } : {}),
    }),
  });
  LastSavedElementsVersion.set(drawingId, sceneVersion);
  return result;
};

/** Backend-agnostic Portal expects a socket param for parity with the old
 * firebase.ts signature; unused here since access control lives server-side. */
export const loadDrawing = async (
  drawingId: string,
  _socket?: Socket,
): Promise<DrawingRecord> => getDrawing(drawingId);

// ---------------------------------------------------------------- settings

export type EditorDefaults = {
  font_family: "hand-drawn" | "normal" | "code";
  font_size: number;
  stroke_color: string;
  background_color: string;
  fill_style: "hachure" | "cross-hatch" | "solid";
  stroke_width: number;
  stroke_style: "solid" | "dashed" | "dotted";
  roughness: number;
  edges: "sharp" | "round";
  arrow_type: "sharp" | "round" | "elbow";
  node_shape: "rectangle" | "ellipse" | "diamond";
};

export type NotificationSettings = {
  product_updates: boolean;
  collaboration_invites: boolean;
  comment_mentions: boolean;
  weekly_digest: boolean;
  security_alerts: boolean;
};

export type UserSettings = {
  email: string;
  username: string | null;
  email_verified: boolean;
  notifications: NotificationSettings;
  editor_defaults: EditorDefaults;
  mcp_endpoint: string;
};

export type McpConnection = {
  client_id: string;
  client_name: string;
  client_uri: string | null;
  scope: string;
  connected_at: string;
  last_used_at: string | null;
  expires_at: string;
};

export const getSettings = (): Promise<UserSettings> =>
  apiFetch("/api/settings");

export const updateProfile = (username: string): Promise<UserSettings> =>
  apiFetch("/api/settings/profile", {
    method: "PATCH",
    body: JSON.stringify({ username }),
  });

export const updateNotifications = (
  notifications: Partial<NotificationSettings>,
): Promise<UserSettings> =>
  apiFetch("/api/settings/notifications", {
    method: "PATCH",
    body: JSON.stringify({ notifications }),
  });

export const updateEditorDefaults = (
  editorDefaults: Partial<EditorDefaults>,
): Promise<UserSettings> =>
  apiFetch("/api/settings/editor-defaults", {
    method: "PATCH",
    body: JSON.stringify({ editor_defaults: editorDefaults }),
  });

export const listMcpConnections = (): Promise<McpConnection[]> =>
  apiFetch("/api/settings/connections");

export const revokeMcpConnection = (clientId: string): Promise<void> =>
  apiFetch(`/api/settings/connections/${clientId}`, { method: "DELETE" });

// ------------------------------------------------------------------- oauth

export type OAuthClientInfo = {
  client_id: string;
  client_name: string;
  client_uri: string | null;
  registered_at: string;
};

export const describeOAuthClient = (
  clientId: string,
): Promise<OAuthClientInfo> => apiFetch(`/api/oauth/clients/${clientId}`);

export const denyOAuthRequest = (params: {
  client_id: string;
  redirect_uri: string;
  state: string;
}): Promise<{ redirect_to: string | null }> =>
  apiFetch("/api/oauth/deny", {
    method: "POST",
    body: JSON.stringify(params),
  });

export const approveOAuthRequest = (params: {
  client_id: string;
  redirect_uri: string;
  state: string;
  code_challenge: string;
  code_challenge_method: string;
  scope: string;
  resource: string | null;
}): Promise<{ redirect_to: string }> =>
  apiFetch("/api/oauth/approve", {
    method: "POST",
    body: JSON.stringify(params),
  });
