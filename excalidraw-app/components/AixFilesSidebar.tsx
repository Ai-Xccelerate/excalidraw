import { Sidebar } from "@excalidraw/excalidraw";
import { useEffect, useMemo, useState } from "react";

import type { ExcalidrawImperativeAPI } from "@excalidraw/excalidraw/types";

import { useAtomValue } from "../app-jotai";

import {
  currentDrawingIdAtom,
  getActiveWorkspaceId,
  listDrawings,
  type DrawingSummary,
} from "../data/backend";

import "./AixFilesSidebar.scss";

const SIDEBAR_NAME = "aix-files";

export const AixFilesSidebar: React.FC<{
  excalidrawAPI: ExcalidrawImperativeAPI | null;
}> = ({ excalidrawAPI }) => {
  const currentDrawingId = useAtomValue(currentDrawingIdAtom);
  const [drawings, setDrawings] = useState<DrawingSummary[] | null>(null);
  // same scope the dashboard is showing, so the sidebar doesn't list drawings
  // from a workspace the user isn't currently looking at
  const workspaceId = getActiveWorkspaceId();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open || drawings) {
      return;
    }
    const load = async () => {
      try {
        const items = await listDrawings();
        setDrawings(
          [...items].sort(
            (a, b) =>
              new Date(b.updated_at).getTime() -
              new Date(a.updated_at).getTime(),
          ),
        );
      } catch {
        setDrawings([]);
      }
    };
    load();
  }, [open, drawings]);

  const scopedDrawings = useMemo(
    () =>
      (drawings ?? []).filter((d) =>
        workspaceId ? d.workspace_id === workspaceId : d.workspace_id === null,
      ),
    [drawings, workspaceId],
  );

  const toggle = () => {
    const next = !open;
    setOpen(next);
    excalidrawAPI?.toggleSidebar({ name: SIDEBAR_NAME, force: next });
    if (next) {
      setDrawings(null);
    }
  };

  return (
    <>
      <button
        className="aix-files-trigger"
        onClick={toggle}
        title="Browse drawings"
        aria-label="Browse drawings"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
          <path
            d="M3 6h6l2 2h10v10a2 2 0 0 1-2 2H3z"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinejoin="round"
          />
        </svg>
      </button>
      <Sidebar
        name={SIDEBAR_NAME}
        docked
        onStateChange={(state) => {
          // fires for whichever sidebar is open (e.g. the library); only sync
          // our own open-state so the trigger doesn't invert against it
          if (!state || state.name === SIDEBAR_NAME) {
            setOpen(state?.name === SIDEBAR_NAME);
          }
        }}
      >
        <Sidebar.Header>
          <span className="aix-files__heading">Your drawings</span>
        </Sidebar.Header>
        <button
          className="aix-files__dashboard"
          onClick={() => window.location.assign("/dashboard")}
        >
          ← Dashboard
        </button>
        <div className="aix-files__list">
          {drawings === null ? (
            <div className="aix-files__empty">Loading…</div>
          ) : scopedDrawings.length === 0 ? (
            <div className="aix-files__empty">No drawings yet.</div>
          ) : (
            scopedDrawings.map((d) => (
              <button
                key={d.id}
                className={`aix-files__item ${
                  d.id === currentDrawingId ? "aix-files__item--active" : ""
                }`}
                onClick={() => window.location.assign(`/d/${d.id}`)}
              >
                <span
                  className="aix-files__thumb"
                  style={
                    d.thumbnail
                      ? { backgroundImage: `url(${d.thumbnail})` }
                      : undefined
                  }
                />
                <span className="aix-files__meta">
                  <span className="aix-files__title">
                    {d.title || "Untitled"}
                  </span>
                  <span className="aix-files__role">{d.role}</span>
                </span>
              </button>
            ))
          )}
        </div>
      </Sidebar>
    </>
  );
};
