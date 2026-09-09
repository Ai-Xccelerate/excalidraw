import { useCallback, useEffect, useState } from "react";

import { useAuth } from "../auth/AuthContext";
import {
  changePassword,
  getSettings,
  listMcpConnections,
  revokeMcpConnection,
  updateEditorDefaults,
  updateNotifications,
  updateProfile,
  type EditorDefaults,
  type McpConnection,
  type NotificationSettings,
  type UserSettings,
} from "../data/backend";

import "./SettingsPage.scss";

type SectionId = "profile" | "password" | "notifications" | "editor" | "agents";

const DOCS_URL = "https://wiki.aiworkforce.md/docs/getdraw";

const SECTIONS: { id: SectionId; label: string; blurb: string }[] = [
  { id: "profile", label: "Profile", blurb: "Your name and account address" },
  {
    id: "password",
    label: "Password",
    blurb: "Change the password you sign in with",
  },
  {
    id: "notifications",
    label: "Notifications",
    blurb: "What we email you about",
  },
  {
    id: "editor",
    label: "Drawing defaults",
    blurb: "How new shapes and text look",
  },
  {
    id: "agents",
    label: "Agents & MCP",
    blurb: "Connect Claude, ChatGPT and other agents",
  },
];

const NOTIFICATION_COPY: {
  key: keyof NotificationSettings;
  label: string;
  hint: string;
}[] = [
  {
    key: "collaboration_invites",
    label: "Collaboration invites",
    hint: "Someone shares a drawing or workspace with you",
  },
  {
    key: "comment_mentions",
    label: "Mentions",
    hint: "You're mentioned in a comment on a drawing",
  },
  {
    key: "security_alerts",
    label: "Security alerts",
    hint: "Password changes and new agent connections",
  },
  {
    key: "product_updates",
    label: "Product updates",
    hint: "New features worth knowing about",
  },
  {
    key: "weekly_digest",
    label: "Weekly digest",
    hint: "A Monday summary of what changed in your workspaces",
  },
];

const FONT_CHOICES: { value: EditorDefaults["font_family"]; label: string }[] =
  [
    { value: "hand-drawn", label: "Hand-drawn" },
    { value: "normal", label: "Normal" },
    { value: "code", label: "Code" },
  ];

const FONT_SIZES = [
  { value: 16, label: "Small" },
  { value: 20, label: "Medium" },
  { value: 28, label: "Large" },
  { value: 36, label: "Extra large" },
];

const STROKE_WIDTHS = [
  { value: 1, label: "Thin" },
  { value: 2, label: "Bold" },
  { value: 4, label: "Extra bold" },
];

const useToast = () => {
  const [message, setMessage] = useState<string | null>(null);
  useEffect(() => {
    if (!message) {
      return;
    }
    const timer = window.setTimeout(() => setMessage(null), 2600);
    return () => window.clearTimeout(timer);
  }, [message]);
  return [message, setMessage] as const;
};

const Field = ({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) => (
  <div className="aix-field">
    <div className="aix-field__text">
      <span className="aix-field__label">{label}</span>
      {hint && <span className="aix-field__hint">{hint}</span>}
    </div>
    <div className="aix-field__control">{children}</div>
  </div>
);

const Choice = <T extends string | number>({
  value,
  options,
  onChange,
}: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
}) => (
  <div className="aix-choice">
    {options.map((option) => (
      <button
        key={String(option.value)}
        type="button"
        className={
          option.value === value
            ? "aix-choice__item aix-choice__item--on"
            : "aix-choice__item"
        }
        onClick={() => onChange(option.value)}
      >
        {option.label}
      </button>
    ))}
  </div>
);

const Toggle = ({
  on,
  onChange,
  label,
}: {
  on: boolean;
  onChange: (on: boolean) => void;
  label: string;
}) => (
  <button
    type="button"
    role="switch"
    aria-checked={on}
    aria-label={label}
    className={on ? "aix-toggle aix-toggle--on" : "aix-toggle"}
    onClick={() => onChange(!on)}
  >
    <span className="aix-toggle__knob" />
  </button>
);

const SettingsPage = () => {
  const { user, refreshUser } = useAuth();
  const [section, setSection] = useState<SectionId>("profile");
  const [settings, setSettings] = useState<UserSettings | null>(null);
  const [connections, setConnections] = useState<McpConnection[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useToast();

  useEffect(() => {
    getSettings()
      .then(setSettings)
      .catch((e) => setError(e.message));
    listMcpConnections()
      .then(setConnections)
      .catch(() => setConnections([]));
  }, []);

  const goBack = () => {
    window.history.pushState({}, "", "/dashboard");
    window.dispatchEvent(new PopStateEvent("popstate"));
  };

  const saveDefaults = useCallback(
    async (patch: Partial<EditorDefaults>) => {
      // optimistic: these are one-click controls, and waiting on a round trip
      // for each makes the whole panel feel laggy
      setSettings((prev) =>
        prev
          ? { ...prev, editor_defaults: { ...prev.editor_defaults, ...patch } }
          : prev,
      );
      try {
        setSettings(await updateEditorDefaults(patch));
        setToast("Saved");
      } catch (e: any) {
        setError(e.message);
      }
    },
    [setToast],
  );

  const saveNotifications = useCallback(
    async (patch: Partial<NotificationSettings>) => {
      setSettings((prev) =>
        prev
          ? { ...prev, notifications: { ...prev.notifications, ...patch } }
          : prev,
      );
      try {
        setSettings(await updateNotifications(patch));
        setToast("Saved");
      } catch (e: any) {
        setError(e.message);
      }
    },
    [setToast],
  );

  return (
    <div className="aix-settings">
      <aside className="aix-settings__nav">
        <button className="aix-settings__back" onClick={goBack}>
          ← Dashboard
        </button>
        <h1 className="aix-settings__title">Settings</h1>
        <nav>
          {SECTIONS.map((item) => (
            <button
              key={item.id}
              className={
                item.id === section
                  ? "aix-settings__navitem aix-settings__navitem--on"
                  : "aix-settings__navitem"
              }
              onClick={() => setSection(item.id)}
            >
              <span>{item.label}</span>
              <small>{item.blurb}</small>
            </button>
          ))}
        </nav>

        <a
          className="aix-settings__docs"
          href={DOCS_URL}
          target="_blank"
          rel="noreferrer"
        >
          Docs
        </a>
      </aside>

      <main className="aix-settings__body">
        {error && (
          <div
            className="aix-settings__error"
            role="alert"
            onClick={() => setError(null)}
          >
            {error}
          </div>
        )}
        {toast && <div className="aix-settings__toast">{toast}</div>}

        {!settings ? (
          <p className="aix-settings__loading">Loading…</p>
        ) : section === "profile" ? (
          <ProfileSection
            settings={settings}
            onSaved={(next) => {
              setSettings(next);
              refreshUser();
              setToast("Profile updated");
            }}
            onError={setError}
          />
        ) : section === "password" ? (
          <PasswordSection
            onDone={() => setToast("Password changed")}
            onError={setError}
          />
        ) : section === "notifications" ? (
          <section className="aix-panel">
            <header>
              <h2>Notifications</h2>
              <p>Email sent to {settings.email}.</p>
            </header>
            {NOTIFICATION_COPY.map((item) => (
              <Field key={item.key} label={item.label} hint={item.hint}>
                <Toggle
                  label={item.label}
                  on={settings.notifications[item.key]}
                  onChange={(on) => saveNotifications({ [item.key]: on })}
                />
              </Field>
            ))}
          </section>
        ) : section === "editor" ? (
          <EditorSection
            defaults={settings.editor_defaults}
            onChange={saveDefaults}
          />
        ) : (
          <AgentsSection
            settings={settings}
            connections={connections}
            onRevoke={async (clientId) => {
              await revokeMcpConnection(clientId);
              setConnections(await listMcpConnections());
              setToast("Disconnected");
            }}
          />
        )}
        <p className="aix-settings__signedin">Signed in as {user?.email}</p>
      </main>
    </div>
  );
};

const ProfileSection = ({
  settings,
  onSaved,
  onError,
}: {
  settings: UserSettings;
  onSaved: (next: UserSettings) => void;
  onError: (message: string) => void;
}) => {
  const [username, setUsername] = useState(settings.username ?? "");
  const [saving, setSaving] = useState(false);

  return (
    <section className="aix-panel">
      <header>
        <h2>Profile</h2>
        <p>How you appear on shared drawings and in collaboration sessions.</p>
      </header>

      <Field label="Display name" hint="Shown to collaborators">
        <input
          className="aix-input"
          value={username}
          placeholder={settings.email.split("@")[0]}
          onChange={(e) => setUsername(e.target.value)}
        />
      </Field>

      <Field
        label="Email"
        hint={
          settings.email_verified
            ? "Verified — this is your sign-in address"
            : "Not verified yet"
        }
      >
        <input className="aix-input" value={settings.email} readOnly disabled />
      </Field>

      <div className="aix-panel__actions">
        <button
          className="aix-btn aix-btn--primary"
          disabled={saving || username === (settings.username ?? "")}
          onClick={async () => {
            setSaving(true);
            try {
              onSaved(await updateProfile(username));
            } catch (e: any) {
              onError(e.message);
            } finally {
              setSaving(false);
            }
          }}
        >
          {saving ? "Saving…" : "Save changes"}
        </button>
      </div>
    </section>
  );
};

const PasswordSection = ({
  onDone,
  onError,
}: {
  onDone: () => void;
  onError: (message: string) => void;
}) => {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [saving, setSaving] = useState(false);

  const mismatch = confirm.length > 0 && next !== confirm;
  const ready = current && next.length >= 8 && next === confirm;

  return (
    <section className="aix-panel">
      <header>
        <h2>Password</h2>
        <p>
          Changing this signs you out everywhere else. Agent connections keep
          working until you disconnect them.
        </p>
      </header>

      <Field label="Current password">
        <input
          className="aix-input"
          type="password"
          autoComplete="current-password"
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
        />
      </Field>
      <Field label="New password" hint="At least 8 characters">
        <input
          className="aix-input"
          type="password"
          autoComplete="new-password"
          value={next}
          onChange={(e) => setNext(e.target.value)}
        />
      </Field>
      <Field
        label="Confirm new password"
        hint={mismatch ? "Passwords don't match" : undefined}
      >
        <input
          className="aix-input"
          type="password"
          autoComplete="new-password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
        />
      </Field>

      <div className="aix-panel__actions">
        <button
          className="aix-btn aix-btn--primary"
          disabled={!ready || saving}
          onClick={async () => {
            setSaving(true);
            try {
              await changePassword(current, next);
              setCurrent("");
              setNext("");
              setConfirm("");
              onDone();
            } catch (e: any) {
              onError(e.message);
            } finally {
              setSaving(false);
            }
          }}
        >
          {saving ? "Changing…" : "Change password"}
        </button>
      </div>
    </section>
  );
};

const EditorSection = ({
  defaults,
  onChange,
}: {
  defaults: EditorDefaults;
  onChange: (patch: Partial<EditorDefaults>) => void;
}) => (
  <section className="aix-panel">
    <header>
      <h2>Drawing defaults</h2>
      <p>
        Applied to new shapes on every canvas — and to the diagrams agents draw
        for you over MCP.
      </p>
    </header>

    <Field label="Font" hint="Text and shape labels">
      <Choice
        value={defaults.font_family}
        options={FONT_CHOICES}
        onChange={(font_family) => onChange({ font_family })}
      />
    </Field>
    <Field label="Font size">
      <Choice
        value={defaults.font_size}
        options={FONT_SIZES}
        onChange={(font_size) => onChange({ font_size })}
      />
    </Field>
    <Field label="Stroke width">
      <Choice
        value={defaults.stroke_width}
        options={STROKE_WIDTHS}
        onChange={(stroke_width) => onChange({ stroke_width })}
      />
    </Field>
    <Field label="Stroke style">
      <Choice
        value={defaults.stroke_style}
        options={[
          { value: "solid" as const, label: "Solid" },
          { value: "dashed" as const, label: "Dashed" },
          { value: "dotted" as const, label: "Dotted" },
        ]}
        onChange={(stroke_style) => onChange({ stroke_style })}
      />
    </Field>
    <Field label="Sloppiness" hint="How hand-drawn the strokes look">
      <Choice
        value={defaults.roughness}
        options={[
          { value: 0, label: "Architect" },
          { value: 1, label: "Artist" },
          { value: 2, label: "Cartoonist" },
        ]}
        onChange={(roughness) => onChange({ roughness })}
      />
    </Field>
    <Field label="Corners">
      <Choice
        value={defaults.edges}
        options={[
          { value: "sharp" as const, label: "Sharp" },
          { value: "round" as const, label: "Round" },
        ]}
        onChange={(edges) => onChange({ edges })}
      />
    </Field>
    <Field label="Arrows">
      <Choice
        value={defaults.arrow_type}
        options={[
          { value: "sharp" as const, label: "Straight" },
          { value: "round" as const, label: "Curved" },
          { value: "elbow" as const, label: "Elbow" },
        ]}
        onChange={(arrow_type) => onChange({ arrow_type })}
      />
    </Field>
    <Field label="Stroke color">
      <input
        className="aix-color"
        type="color"
        value={defaults.stroke_color}
        onChange={(e) => onChange({ stroke_color: e.target.value })}
      />
    </Field>
    <Field label="Diagram node shape" hint="Default box shape agents draw with">
      <Choice
        value={defaults.node_shape}
        options={[
          { value: "rectangle" as const, label: "Rectangle" },
          { value: "ellipse" as const, label: "Ellipse" },
          { value: "diamond" as const, label: "Diamond" },
        ]}
        onChange={(node_shape) => onChange({ node_shape })}
      />
    </Field>
  </section>
);

const AgentsSection = ({
  settings,
  connections,
  onRevoke,
}: {
  settings: UserSettings;
  connections: McpConnection[];
  onRevoke: (clientId: string) => Promise<void>;
}) => {
  const [copied, setCopied] = useState(false);

  return (
    <section className="aix-panel">
      <header>
        <h2>Agents &amp; MCP</h2>
        <p>
          getdraw.app speaks MCP, so Claude, ChatGPT and any other agent that
          supports it can list your drawings and draw diagrams for you — using
          the defaults you set here.
        </p>
      </header>

      <div className="aix-endpoint">
        <span className="aix-endpoint__label">Connection URL</span>
        <code className="aix-endpoint__value">{settings.mcp_endpoint}</code>
        <button
          className="aix-btn"
          onClick={async () => {
            await navigator.clipboard.writeText(settings.mcp_endpoint);
            setCopied(true);
            window.setTimeout(() => setCopied(false), 1800);
          }}
        >
          {copied ? "Copied" : "Copy"}
        </button>
      </div>

      <ol className="aix-steps">
        <li>Add the URL above as a custom MCP connector in your agent.</li>
        <li>
          It sends you here to sign in and approve — nothing is shared until you
          do.
        </li>
        <li>
          Then ask for a drawing:{" "}
          <em>"make a flowchart of our onboarding in getdraw.app"</em>.
        </li>
      </ol>

      <h3 className="aix-panel__subhead">Connected agents</h3>
      {connections.length === 0 ? (
        <p className="aix-empty">
          Nothing connected yet. Approved agents show up here, and you can cut
          them off at any time.
        </p>
      ) : (
        <ul className="aix-connections">
          {connections.map((connection) => (
            <li key={connection.client_id} className="aix-connection">
              <div className="aix-connection__identity">
                <span className="aix-connection__name">
                  {connection.client_name}
                </span>
                <span className="aix-connection__meta">
                  {connection.scope.split(" ").join(" · ")}
                  {connection.last_used_at
                    ? ` — last used ${new Date(
                        connection.last_used_at,
                      ).toLocaleString()}`
                    : " — not used yet"}
                </span>
              </div>
              <button
                className="aix-btn aix-btn--danger"
                onClick={() => onRevoke(connection.client_id)}
              >
                Disconnect
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
};

export default SettingsPage;
