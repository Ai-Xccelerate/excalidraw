import clsx from "clsx";
import { useEffect, useMemo, useRef, useState } from "react";

import { SignedIn, SignedOut, useAuth } from "../auth/AuthContext";

import {
  createCollection,
  createDrawing,
  deleteCollection,
  deleteDrawing,
  emptyTrash,
  listCollections,
  listDrawings,
  listTrash,
  purgeDrawing,
  restoreDrawing,
  listWorkspaces,
  getActiveWorkspaceId,
  setActiveWorkspaceId,
  moveDrawing,
  type Workspace,
  renameCollection,
  renameDrawing,
  type CollectionRecord,
  type DrawingSummary,
} from "../data/backend";

import "./DashboardPage.scss";

const LOGO = "/logo.png";
// the square mark, for places too small for the full lockup
const LOGO_MARK = "/logo-mark.png";

const settingsIcon = (
  <svg
    viewBox="0 0 24 24"
    width="16"
    height="16"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.7"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <circle cx="12" cy="12" r="3" />
    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.6a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9c.2.61.77 1.02 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
  </svg>
);

const signOutIcon = (
  <svg
    viewBox="0 0 24 24"
    width="16"
    height="16"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.7"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
    <polyline points="16 17 21 12 16 7" />
    <line x1="21" y1="12" x2="9" y2="12" />
  </svg>
);

const trashIcon = (
  <svg
    viewBox="0 0 24 24"
    width="15"
    height="15"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.7"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <polyline points="3 6 5 6 21 6" />
    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
  </svg>
);

const gridIcon = (
  <svg viewBox="0 0 24 24" width="15" height="15" fill="currentColor">
    <rect x="3" y="3" width="8" height="8" rx="1.5" />
    <rect x="13" y="3" width="8" height="8" rx="1.5" />
    <rect x="3" y="13" width="8" height="8" rx="1.5" />
    <rect x="13" y="13" width="8" height="8" rx="1.5" />
  </svg>
);

const listIcon = (
  <svg viewBox="0 0 24 24" width="15" height="15" fill="currentColor">
    <rect x="3" y="4" width="18" height="3" rx="1.5" />
    <rect x="3" y="10.5" width="18" height="3" rx="1.5" />
    <rect x="3" y="17" width="18" height="3" rx="1.5" />
  </svg>
);

const searchIcon = (
  <svg
    viewBox="0 0 24 24"
    width="15"
    height="15"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
  >
    <circle cx="11" cy="11" r="7" />
    <line x1="16.5" y1="16.5" x2="21" y2="21" />
  </svg>
);

const VIEW_KEY = "aixdraw-dashboard-view";
const SORT_KEY = "aixdraw-dashboard-sort";

type SortKey = "recent" | "oldest" | "az" | "za";
type FilterKey = "all" | "mine" | "shared" | "unfiled";

const SORT_LABELS: Record<SortKey, string> = {
  recent: "Last modified",
  oldest: "Oldest first",
  az: "Name A–Z",
  za: "Name Z–A",
};

const FILTER_LABELS: Record<FilterKey, string> = {
  all: "All drawings",
  mine: "Owned by me",
  shared: "Shared with me",
  unfiled: "Not in a collection",
};

const readStored = <T extends string>(key: string, fallback: T): T => {
  try {
    return (window.localStorage.getItem(key) as T | null) ?? fallback;
  } catch {
    return fallback;
  }
};

/** the Trash behaves like a collection in the sidebar, but it isn't one — no
 * row in the collections table has this id */
const TRASH_VIEW = "__trash__";

const daysUntil = (iso: string): number =>
  Math.max(0, Math.ceil((new Date(iso).getTime() - Date.now()) / 86400000));

const relativeTime = (iso: string): string => {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.round(diff / 60000);
  if (mins < 1) {
    return "just now";
  }
  if (mins < 60) {
    return `${mins} min ago`;
  }
  const hours = Math.round(mins / 60);
  if (hours < 24) {
    return `${hours} hr ago`;
  }
  const days = Math.round(hours / 24);
  if (days < 30) {
    return `${days} day${days === 1 ? "" : "s"} ago`;
  }
  const months = Math.round(days / 30);
  return `${months} mo ago`;
};

const openDrawing = (id: string) => window.location.assign(`/d/${id}`);

type ViewMode = "grid" | "list";

/** the ⋯ menu is the same set of actions in both layouts, so it lives in one
 * place rather than being written out twice */
const DrawingMenu = ({
  drawing,
  collections,
  onChanged,
  onRename,
}: {
  drawing: DrawingSummary;
  collections: CollectionRecord[];
  onChanged: () => void;
  onRename: () => void;
}) => {
  const [menuOpen, setMenuOpen] = useState(false);
  const actionsRef = useRef<HTMLDivElement>(null);

  // close the ⋯ menu on any click outside it (the kebab itself still toggles)
  useEffect(() => {
    if (!menuOpen) {
      return;
    }
    const onDown = (event: MouseEvent) => {
      if (
        actionsRef.current &&
        !actionsRef.current.contains(event.target as Node)
      ) {
        setMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [menuOpen]);

  return (
    <div className="aix-card__actions" ref={actionsRef}>
      <button
        className="aix-kebab"
        onClick={() => setMenuOpen((v) => !v)}
        aria-label="Drawing actions"
      >
        ⋯
      </button>
      {menuOpen && (
        <div className="aix-menu">
          <button
            onClick={() => {
              setMenuOpen(false);
              onRename();
            }}
          >
            Rename
          </button>
          {collections.length > 0 && (
            <div className="aix-menu__group">
              <div className="aix-menu__label">Move to</div>
              <button
                onClick={async () => {
                  setMenuOpen(false);
                  await moveDrawing(drawing.id, null);
                  onChanged();
                }}
              >
                No collection
              </button>
              {collections.map((c) => (
                <button
                  key={c.id}
                  onClick={async () => {
                    setMenuOpen(false);
                    await moveDrawing(drawing.id, c.id);
                    onChanged();
                  }}
                >
                  {c.name}
                </button>
              ))}
            </div>
          )}
          {drawing.role === "owner" && (
            <button
              className="aix-menu__danger"
              onClick={async () => {
                setMenuOpen(false);
                await deleteDrawing(drawing.id);
                onChanged();
              }}
            >
              Move to Trash
            </button>
          )}
        </div>
      )}
    </div>
  );
};

const DrawingCard = ({
  drawing,
  collections,
  view,
  onChanged,
}: {
  drawing: DrawingSummary;
  collections: CollectionRecord[];
  view: ViewMode;
  onChanged: () => void;
}) => {
  const [renaming, setRenaming] = useState(false);
  const [title, setTitle] = useState(drawing.title || "Untitled");
  const canEdit = drawing.role === "owner" || drawing.role === "editor";

  const commitRename = async () => {
    setRenaming(false);
    const trimmed = title.trim();
    if (trimmed && trimmed !== drawing.title) {
      await renameDrawing(drawing.id, trimmed);
      onChanged();
    } else {
      setTitle(drawing.title || "Untitled");
    }
  };

  const nameField = renaming ? (
    <input
      autoFocus
      value={title}
      onChange={(e) => setTitle(e.target.value)}
      onBlur={commitRename}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          commitRename();
        } else if (e.key === "Escape") {
          setTitle(drawing.title || "Untitled");
          setRenaming(false);
        }
      }}
    />
  ) : (
    <div className="aix-card__title" onClick={() => openDrawing(drawing.id)}>
      {drawing.title || "Untitled"}
    </div>
  );

  const menu = canEdit ? (
    <DrawingMenu
      drawing={drawing}
      collections={collections}
      onChanged={onChanged}
      onRename={() => setRenaming(true)}
    />
  ) : null;

  // an owner can file a drawing away by dragging it onto a collection in the
  // sidebar; the id travels as plain text so the drop handler stays trivial
  const dragProps = canEdit
    ? {
        draggable: true,
        onDragStart: (event: React.DragEvent) => {
          event.dataTransfer.setData("text/plain", drawing.id);
          event.dataTransfer.effectAllowed = "move";
        },
      }
    : {};

  if (view === "list") {
    return (
      <div className="aix-row" {...dragProps}>
        <button
          className="aix-row__thumb"
          onClick={() => openDrawing(drawing.id)}
          style={
            drawing.thumbnail
              ? { backgroundImage: `url(${drawing.thumbnail})` }
              : undefined
          }
        >
          {!drawing.thumbnail && <img src={LOGO_MARK} alt="" aria-hidden />}
        </button>
        <div className="aix-row__name">{nameField}</div>
        <div className="aix-row__collection">
          {collections.find((c) => c.id === drawing.collection_id)?.name ?? "—"}
        </div>
        <div className="aix-row__role">{drawing.role}</div>
        <div className="aix-row__age">{relativeTime(drawing.updated_at)}</div>
        {menu}
      </div>
    );
  }

  return (
    <div className="aix-card" {...dragProps}>
      <button
        className="aix-card__thumb"
        onClick={() => openDrawing(drawing.id)}
        style={
          drawing.thumbnail
            ? { backgroundImage: `url(${drawing.thumbnail})` }
            : undefined
        }
      >
        {!drawing.thumbnail && <img src={LOGO_MARK} alt="" aria-hidden />}
        <span className="aix-card__age">
          {relativeTime(drawing.updated_at)}
        </span>
      </button>
      <div className="aix-card__meta">
        <div className="aix-card__info">
          {nameField}
          <div className="aix-card__role">{drawing.role}</div>
        </div>
        {menu}
      </div>
    </div>
  );
};

const TrashCard = ({
  drawing,
  onChanged,
}: {
  drawing: DrawingSummary;
  onChanged: () => void;
}) => {
  const [busy, setBusy] = useState(false);
  const left = drawing.purges_at ? daysUntil(drawing.purges_at) : null;

  return (
    <div className="aix-card aix-card--trashed">
      <div
        className="aix-card__thumb aix-card__thumb--static"
        style={
          drawing.thumbnail
            ? { backgroundImage: `url(${drawing.thumbnail})` }
            : undefined
        }
      >
        {!drawing.thumbnail && <img src={LOGO_MARK} alt="" aria-hidden />}
        {drawing.deleted_at && (
          <span className="aix-card__age">
            deleted {relativeTime(drawing.deleted_at)}
          </span>
        )}
      </div>
      <div className="aix-card__meta">
        <div className="aix-card__info">
          <div className="aix-card__title">{drawing.title || "Untitled"}</div>
          <div className="aix-card__role">
            {left === null
              ? "in the Trash"
              : left === 0
              ? "purges today"
              : `${left} day${left === 1 ? "" : "s"} left`}
          </div>
        </div>
      </div>
      <div className="aix-card__trash-actions">
        <button
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              await restoreDrawing(drawing.id);
              onChanged();
            } finally {
              setBusy(false);
            }
          }}
        >
          Restore
        </button>
        <button
          className="aix-menu__danger"
          disabled={busy}
          onClick={async () => {
            // eslint-disable-next-line no-alert
            if (
              !window.confirm(
                `Delete “${
                  drawing.title || "Untitled"
                }” for good? This can't be undone.`,
              )
            ) {
              return;
            }
            setBusy(true);
            try {
              await purgeDrawing(drawing.id);
              onChanged();
            } finally {
              setBusy(false);
            }
          }}
        >
          Delete forever
        </button>
      </div>
    </div>
  );
};

const DashboardShell = () => {
  const { user, logout } = useAuth();

  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspaceId, setWorkspaceIdState] = useState<string | null>(
    getActiveWorkspaceId(),
  );

  // the active workspace also travels on the X-Workspace-Id header, so it has
  // to be persisted rather than kept in component state alone
  const selectWorkspace = (id: string | null) => {
    setActiveWorkspaceId(id);
    setWorkspaceIdState(id);
  };
  const [drawings, setDrawings] = useState<DrawingSummary[] | null>(null);
  const [trash, setTrash] = useState<DrawingSummary[]>([]);
  const [collections, setCollections] = useState<CollectionRecord[]>([]);
  const [activeCollectionId, setActiveCollectionId] = useState<string | null>(
    null,
  );
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<SortKey>(() =>
    readStored<SortKey>(SORT_KEY, "recent"),
  );
  const [filter, setFilter] = useState<FilterKey>("all");
  const [view, setView] = useState<ViewMode>(() =>
    readStored<ViewMode>(VIEW_KEY, "grid"),
  );
  const [dropTarget, setDropTarget] = useState<string | null>(null);
  const [addingCollection, setAddingCollection] = useState(false);
  const [newCollectionName, setNewCollectionName] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listWorkspaces()
      .then((wss) => {
        if (cancelled) {
          return;
        }
        setWorkspaces(wss);
        // a stored id from a workspace the user was removed from would keep
        // sending a header the API rejects, so fall back to personal
        if (workspaceId && !wss.some((w) => w.id === workspaceId)) {
          selectWorkspace(null);
        }
      })
      .catch((e) => setError(e.message));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const refresh = () => {
    listDrawings()
      .then(setDrawings)
      .catch((e) => setError(e.message));
    listCollections(workspaceId)
      .then(setCollections)
      .catch((e) => setError(e.message));
    listTrash()
      .then(setTrash)
      .catch((e) => setError(e.message));
  };

  useEffect(() => {
    setActiveCollectionId(null);
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId]);

  const trashOpen = activeCollectionId === TRASH_VIEW;

  const setViewMode = (next: ViewMode) => {
    setView(next);
    try {
      window.localStorage.setItem(VIEW_KEY, next);
    } catch {
      // a lost preference is not worth failing the click over
    }
  };

  const setSortKey = (next: SortKey) => {
    setSort(next);
    try {
      window.localStorage.setItem(SORT_KEY, next);
    } catch {
      // as above
    }
  };

  const search = (list: DrawingSummary[]) => {
    const needle = query.trim().toLowerCase();
    if (!needle) {
      return list;
    }
    return list.filter((d) =>
      (d.title || "Untitled").toLowerCase().includes(needle),
    );
  };

  const sortList = (list: DrawingSummary[]) =>
    [...list].sort((a, b) => {
      const at = new Date(a.updated_at).getTime();
      const bt = new Date(b.updated_at).getTime();
      const an = (a.title || "Untitled").toLowerCase();
      const bn = (b.title || "Untitled").toLowerCase();
      switch (sort) {
        case "oldest":
          return at - bt;
        case "az":
          return an.localeCompare(bn);
        case "za":
          return bn.localeCompare(an);
        default:
          return bt - at;
      }
    });

  /** files a drawing into a collection by drag, then clears the highlight */
  const dropInto = async (
    event: React.DragEvent,
    collectionId: string | null,
  ) => {
    event.preventDefault();
    setDropTarget(null);
    const id = event.dataTransfer.getData("text/plain");
    if (!id) {
      return;
    }
    try {
      await moveDrawing(id, collectionId);
      refresh();
    } catch (e: any) {
      setError(e.message);
    }
  };

  const dropProps = (key: string, collectionId: string | null) => ({
    onDragOver: (event: React.DragEvent) => {
      event.preventDefault();
      event.dataTransfer.dropEffect = "move";
      setDropTarget(key);
    },
    onDragLeave: () => setDropTarget((t) => (t === key ? null : t)),
    onDrop: (event: React.DragEvent) => dropInto(event, collectionId),
  });

  const inScope = (d: DrawingSummary) =>
    workspaceId ? d.workspace_id === workspaceId : d.workspace_id === null;

  const scopeDrawings = useMemo(() => {
    if (!drawings) {
      return [];
    }
    const filtered = drawings
      .filter(inScope)
      .filter((d) =>
        activeCollectionId && activeCollectionId !== TRASH_VIEW
          ? d.collection_id === activeCollectionId
          : true,
      )
      .filter((d) => {
        switch (filter) {
          case "mine":
            return d.role === "owner";
          case "shared":
            return d.role !== "owner";
          case "unfiled":
            return d.collection_id === null;
          default:
            return true;
        }
      });
    return sortList(search(filtered));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [drawings, workspaceId, activeCollectionId, filter, query, sort]);

  const sharedDrawings = useMemo(() => {
    if (!drawings) {
      return [];
    }
    return sortList(
      search(drawings.filter((d) => d.role !== "owner" && !inScope(d))),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [drawings, workspaceId, query, sort]);

  const startDrawing = async () => {
    try {
      const drawing = await createDrawing(
        "Untitled",
        activeCollectionId === TRASH_VIEW ? null : activeCollectionId,
      );
      openDrawing(drawing.id);
    } catch (e: any) {
      setError(e.message);
    }
  };

  const addCollection = async () => {
    const name = newCollectionName.trim();
    setAddingCollection(false);
    setNewCollectionName("");
    if (!name) {
      return;
    }
    await createCollection(name, workspaceId);
    refresh();
  };

  return (
    <div className="aix-dashboard">
      <aside className="aix-sidebar">
        <div className="aix-sidebar__top">
          <img
            className="aix-sidebar__logo"
            src={LOGO}
            alt="draw.getdraw.app"
          />
        </div>

        <nav className="aix-nav">
          <button className="aix-nav__item aix-nav__item--active">
            Dashboard
          </button>
        </nav>

        <div className="aix-collections">
          <div className="aix-collections__head">
            <span>Collections</span>
            <button
              className="aix-collections__add"
              onClick={() => setAddingCollection(true)}
              aria-label="New collection"
            >
              +
            </button>
          </div>
          <button
            className={clsx("aix-nav__item", {
              "aix-nav__item--active": activeCollectionId === null,
              "aix-nav__item--drop": dropTarget === "all",
            })}
            onClick={() => setActiveCollectionId(null)}
            {...dropProps("all", null)}
          >
            All drawings
          </button>
          {addingCollection && (
            <input
              className="aix-collection__input"
              autoFocus
              placeholder="Collection name"
              value={newCollectionName}
              onChange={(e) => setNewCollectionName(e.target.value)}
              onBlur={addCollection}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  addCollection();
                } else if (e.key === "Escape") {
                  setAddingCollection(false);
                  setNewCollectionName("");
                }
              }}
            />
          )}
          {collections.map((c) => (
            <CollectionRow
              key={c.id}
              collection={c}
              active={activeCollectionId === c.id}
              dropping={dropTarget === c.id}
              dropProps={dropProps(c.id, c.id)}
              onSelect={() => setActiveCollectionId(c.id)}
              onChanged={refresh}
              onDeleted={() => {
                if (activeCollectionId === c.id) {
                  setActiveCollectionId(null);
                }
                refresh();
              }}
            />
          ))}

          <button
            className={`aix-nav__item aix-nav__item--trash ${
              trashOpen ? "aix-nav__item--active" : ""
            }`}
            onClick={() => setActiveCollectionId(TRASH_VIEW)}
          >
            <span className="aix-nav__icon">{trashIcon}</span>
            Trash
            {trash.length > 0 && (
              <span className="aix-nav__count">{trash.length}</span>
            )}
          </button>
        </div>

        <div className="aix-sidebar__bottom">
          {/* a solo account has one place for its drawings, so there is nothing
              to choose between — the picker appears once a shared workspace
              actually exists */}
          {workspaces.length > 0 && (
            <label className="aix-workspace-picker">
              <span className="aix-workspace-picker__label">Workspace</span>
              <select
                className="aix-workspace-picker__select"
                value={workspaceId ?? ""}
                onChange={(e) => selectWorkspace(e.target.value || null)}
              >
                <option value="">Personal</option>
                {workspaces.map((w) => (
                  <option key={w.id} value={w.id}>
                    {w.name}
                  </option>
                ))}
              </select>
            </label>
          )}

          <div className="aix-account">
            <div className="aix-account__avatar" aria-hidden="true">
              {(user?.username || user?.email || "?").charAt(0).toUpperCase()}
            </div>
            <div className="aix-account__identity">
              <span className="aix-account__name">
                {user?.username || user?.email?.split("@")[0] || "Account"}
              </span>
              <span className="aix-account__email" title={user?.email}>
                {user?.email}
              </span>
            </div>
            <div className="aix-account__actions">
              <button
                className="aix-icon-btn"
                title="Settings"
                aria-label="Settings"
                onClick={() => {
                  window.history.pushState({}, "", "/settings");
                  window.dispatchEvent(new PopStateEvent("popstate"));
                }}
              >
                {settingsIcon}
              </button>
              <button
                className="aix-icon-btn"
                title="Sign out"
                aria-label="Sign out"
                onClick={logout}
              >
                {signOutIcon}
              </button>
            </div>
          </div>
        </div>
      </aside>

      <main className="aix-main">
        <header className="aix-main__header">
          <h1>{trashOpen ? "Trash" : "Dashboard"}</h1>
          {trashOpen ? (
            trash.length > 0 && (
              <button
                className="aix-start-btn aix-start-btn--danger"
                onClick={async () => {
                  // eslint-disable-next-line no-alert
                  if (
                    !window.confirm(
                      `Delete all ${trash.length} drawing${
                        trash.length === 1 ? "" : "s"
                      } in the Trash for good? This can't be undone.`,
                    )
                  ) {
                    return;
                  }
                  try {
                    await emptyTrash();
                    refresh();
                  } catch (e: any) {
                    setError(e.message);
                  }
                }}
              >
                Empty trash
              </button>
            )
          ) : (
            <button className="aix-start-btn" onClick={startDrawing}>
              Start drawing
            </button>
          )}
        </header>

        {error && <div className="aix-error">{error}</div>}

        {!trashOpen && (
          <div className="aix-toolbar">
            <label className="aix-search">
              <span className="aix-search__icon">{searchIcon}</span>
              <input
                type="search"
                placeholder="Search drawings"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </label>

            <select
              className="aix-select"
              aria-label="Filter drawings"
              value={filter}
              onChange={(e) => setFilter(e.target.value as FilterKey)}
            >
              {(Object.keys(FILTER_LABELS) as FilterKey[]).map((key) => (
                <option key={key} value={key}>
                  {FILTER_LABELS[key]}
                </option>
              ))}
            </select>

            <select
              className="aix-select"
              aria-label="Sort drawings"
              value={sort}
              onChange={(e) => setSortKey(e.target.value as SortKey)}
            >
              {(Object.keys(SORT_LABELS) as SortKey[]).map((key) => (
                <option key={key} value={key}>
                  {SORT_LABELS[key]}
                </option>
              ))}
            </select>

            <div className="aix-viewtoggle">
              <button
                className={view === "grid" ? "is-active" : ""}
                onClick={() => setViewMode("grid")}
                aria-label="Grid view"
                aria-pressed={view === "grid"}
                title="Grid view"
              >
                {gridIcon}
              </button>
              <button
                className={view === "list" ? "is-active" : ""}
                onClick={() => setViewMode("list")}
                aria-label="List view"
                aria-pressed={view === "list"}
                title="List view"
              >
                {listIcon}
              </button>
            </div>
          </div>
        )}

        {trashOpen ? (
          <section>
            <p className="aix-trash-note">
              Deleted drawings stay here for 90 days, then are removed for good.
            </p>
            {trash.length === 0 ? (
              <div className="aix-empty">The Trash is empty.</div>
            ) : (
              <div className="aix-grid">
                {trash.map((d) => (
                  <TrashCard key={d.id} drawing={d} onChanged={refresh} />
                ))}
              </div>
            )}
          </section>
        ) : (
          <section>
            <h2>
              {activeCollectionId
                ? collections.find((c) => c.id === activeCollectionId)?.name
                : "Recently modified"}
            </h2>
            {drawings === null ? (
              <div className="aix-empty">Loading…</div>
            ) : scopeDrawings.length === 0 ? (
              <div className="aix-empty">
                {query.trim()
                  ? `Nothing matches “${query.trim()}”.`
                  : "No drawings here yet. Hit “Start drawing” to create one."}
              </div>
            ) : (
              <div className={view === "list" ? "aix-list" : "aix-grid"}>
                {view === "list" && (
                  <div className="aix-row aix-row--head">
                    <span />
                    <div className="aix-row__name">Name</div>
                    <div className="aix-row__collection">Collection</div>
                    <div className="aix-row__role">Role</div>
                    <div className="aix-row__age">Modified</div>
                    <span />
                  </div>
                )}
                {scopeDrawings.map((d) => (
                  <DrawingCard
                    key={d.id}
                    drawing={d}
                    collections={collections}
                    view={view}
                    onChanged={refresh}
                  />
                ))}
              </div>
            )}
          </section>
        )}

        {!trashOpen && sharedDrawings.length > 0 && (
          <section>
            <h2>Shared with you</h2>
            <div className={view === "list" ? "aix-list" : "aix-grid"}>
              {sharedDrawings.map((d) => (
                <DrawingCard
                  key={d.id}
                  drawing={d}
                  collections={collections}
                  view={view}
                  onChanged={refresh}
                />
              ))}
            </div>
          </section>
        )}
      </main>
    </div>
  );
};

const CollectionRow = ({
  collection,
  active,
  dropping,
  dropProps,
  onSelect,
  onChanged,
  onDeleted,
}: {
  collection: CollectionRecord;
  active: boolean;
  dropping: boolean;
  dropProps: {
    onDragOver: (event: React.DragEvent) => void;
    onDragLeave: () => void;
    onDrop: (event: React.DragEvent) => void;
  };
  onSelect: () => void;
  onChanged: () => void;
  onDeleted: () => void;
}) => {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(collection.name);

  const commit = async () => {
    setEditing(false);
    const trimmed = name.trim();
    if (trimmed && trimmed !== collection.name) {
      await renameCollection(collection.id, trimmed);
      onChanged();
    } else {
      setName(collection.name);
    }
  };

  if (editing) {
    return (
      <input
        className="aix-collection__input"
        autoFocus
        value={name}
        onChange={(e) => setName(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            commit();
          } else if (e.key === "Escape") {
            setName(collection.name);
            setEditing(false);
          }
        }}
      />
    );
  }

  return (
    <div
      className={clsx("aix-collection", {
        "aix-collection--active": active,
        "aix-collection--drop": dropping,
      })}
      {...dropProps}
    >
      <button className="aix-collection__name" onClick={onSelect}>
        {collection.name}
      </button>
      <button
        className="aix-collection__edit"
        onClick={() => setEditing(true)}
        aria-label="Rename collection"
      >
        ✎
      </button>
      <button
        className="aix-collection__del"
        onClick={async () => {
          await deleteCollection(collection.id);
          onDeleted();
        }}
        aria-label="Delete collection"
      >
        ×
      </button>
    </div>
  );
};

export const DashboardPage = () => (
  <>
    <SignedIn>
      <DashboardShell />
    </SignedIn>
    <SignedOut>
      <div className="aix-signedout">
        <img src={LOGO} alt="draw.getdraw.app" />
        <p>Sign in to see your drawings and workspaces.</p>
        <button
          className="aix-start-btn"
          onClick={() => {
            window.location.href = "/login";
          }}
        >
          Sign in
        </button>
        <a href="/">Continue without an account</a>
      </div>
    </SignedOut>
  </>
);
