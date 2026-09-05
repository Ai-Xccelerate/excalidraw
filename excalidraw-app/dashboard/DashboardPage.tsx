import clsx from "clsx";
import { useEffect, useMemo, useRef, useState } from "react";

import { SignedIn, SignedOut, useAuth } from "../auth/AuthContext";

import {
  createCollection,
  createDrawing,
  deleteCollection,
  deleteDrawing,
  listCollections,
  listDrawings,
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

const LOGO_LIGHT = "/aix-logo.png";

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

const DrawingCard = ({
  drawing,
  collections,
  onChanged,
}: {
  drawing: DrawingSummary;
  collections: CollectionRecord[];
  onChanged: () => void;
}) => {
  const [menuOpen, setMenuOpen] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [title, setTitle] = useState(drawing.title || "Untitled");
  const canEdit = drawing.role === "owner" || drawing.role === "editor";
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

  return (
    <div className={clsx("aix-card", { "aix-card--menu-open": menuOpen })}>
      <button
        className="aix-card__thumb"
        onClick={() => openDrawing(drawing.id)}
        style={
          drawing.thumbnail
            ? { backgroundImage: `url(${drawing.thumbnail})` }
            : undefined
        }
      >
        {!drawing.thumbnail && <img src={LOGO_LIGHT} alt="" aria-hidden />}
        <span className="aix-card__age">
          {relativeTime(drawing.updated_at)}
        </span>
      </button>
      <div className="aix-card__meta">
        <div className="aix-card__info">
          {renaming ? (
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
            <div
              className="aix-card__title"
              onClick={() => openDrawing(drawing.id)}
            >
              {drawing.title || "Untitled"}
            </div>
          )}
          <div className="aix-card__role">{drawing.role}</div>
        </div>
        {canEdit && (
          <div className="aix-card__actions" ref={actionsRef}>
            <button
              className="aix-kebab"
              onClick={() => setMenuOpen((v) => !v)}
              aria-label="Drawing actions"
            >
              ⋯
            </button>
            {menuOpen && (
              <>
                <div className="aix-menu">
                  <button
                    onClick={() => {
                      setMenuOpen(false);
                      setRenaming(true);
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
                      Delete
                    </button>
                  )}
                </div>
              </>
            )}
          </div>
        )}
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
  const [collections, setCollections] = useState<CollectionRecord[]>([]);
  const [activeCollectionId, setActiveCollectionId] = useState<string | null>(
    null,
  );
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
  };

  useEffect(() => {
    setActiveCollectionId(null);
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId]);

  const inScope = (d: DrawingSummary) =>
    workspaceId ? d.workspace_id === workspaceId : d.workspace_id === null;

  const scopeDrawings = useMemo(() => {
    if (!drawings) {
      return [];
    }
    return drawings
      .filter(inScope)
      .filter((d) =>
        activeCollectionId ? d.collection_id === activeCollectionId : true,
      )
      .sort(
        (a, b) =>
          new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
      );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [drawings, workspaceId, activeCollectionId]);

  const sharedDrawings = useMemo(() => {
    if (!drawings) {
      return [];
    }
    return drawings
      .filter((d) => d.role !== "owner" && !inScope(d))
      .sort(
        (a, b) =>
          new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
      );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [drawings, workspaceId]);

  const startDrawing = async () => {
    try {
      const drawing = await createDrawing("Untitled", activeCollectionId);
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
          <img className="aix-sidebar__logo" src={LOGO_LIGHT} alt="AIX Draw" />
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
            className={`aix-nav__item ${
              activeCollectionId === null ? "aix-nav__item--active" : ""
            }`}
            onClick={() => setActiveCollectionId(null)}
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
        </div>

        <div className="aix-sidebar__bottom">
          <div className="aix-sidebar__workspace">
            <select
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
          </div>
          <div className="aix-sidebar__user">
            <span>{user?.username || user?.email || "Account"}</span>
            <button className="aix-signout-btn" onClick={logout}>
              Sign out
            </button>
          </div>
        </div>
      </aside>

      <main className="aix-main">
        <header className="aix-main__header">
          <h1>Dashboard</h1>
          <button className="aix-start-btn" onClick={startDrawing}>
            Start drawing
          </button>
        </header>

        {error && <div className="aix-error">{error}</div>}

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
              No drawings here yet. Hit “Start drawing” to create one.
            </div>
          ) : (
            <div className="aix-grid">
              {scopeDrawings.map((d) => (
                <DrawingCard
                  key={d.id}
                  drawing={d}
                  collections={collections}
                  onChanged={refresh}
                />
              ))}
            </div>
          )}
        </section>

        {sharedDrawings.length > 0 && (
          <section>
            <h2>Shared with you</h2>
            <div className="aix-grid">
              {sharedDrawings.map((d) => (
                <DrawingCard
                  key={d.id}
                  drawing={d}
                  collections={collections}
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
  onSelect,
  onChanged,
  onDeleted,
}: {
  collection: CollectionRecord;
  active: boolean;
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
    <div className={`aix-collection ${active ? "aix-collection--active" : ""}`}>
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
        <img src={LOGO_LIGHT} alt="AIX Draw" />
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
