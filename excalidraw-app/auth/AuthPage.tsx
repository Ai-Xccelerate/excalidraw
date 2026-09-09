import React, { useEffect, useState } from "react";

import { useAuth } from "./AuthContext";

import "./AuthPage.scss";

type Mode = "login" | "signup" | "forgot" | "reset" | "verify";

const describe = (error: unknown): string =>
  error instanceof Error ? error.message : "Something went wrong. Try again.";

const COPY: Record<Mode, { title: string; subtitle: string; submit: string }> =
  {
    login: {
      title: "Sign in to draw.getdraw.app",
      subtitle: "Welcome back! Please sign in to continue.",
      submit: "Continue",
    },
    signup: {
      title: "Create your draw.getdraw.app account",
      subtitle: "Start drawing in seconds.",
      submit: "Create account",
    },
    forgot: {
      title: "Reset your password",
      subtitle: "We'll email you a link to set a new one.",
      submit: "Send reset link",
    },
    reset: {
      title: "Choose a new password",
      subtitle: "Pick something you haven't used before.",
      submit: "Set new password",
    },
    verify: {
      title: "Verifying your email",
      subtitle: "One moment while we confirm your address.",
      submit: "Continue",
    },
  };

export const AuthPage = ({
  initialMode = "login",
  resetToken = null,
  verifyToken = null,
}: {
  initialMode?: Mode;
  resetToken?: string | null;
  verifyToken?: string | null;
}) => {
  const auth = useAuth();
  const [mode, setMode] = useState<Mode>(initialMode);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // the verification link lands here with a token and nothing to fill in, so
  // redeem it on arrival rather than making the user press another button
  useEffect(() => {
    if (initialMode !== "verify") {
      return;
    }
    if (!verifyToken) {
      setError("That verification link is missing its token.");
      setMode("login");
      return;
    }
    auth
      .verifyEmail(verifyToken)
      .then(() => {
        window.location.href = "/dashboard";
      })
      .catch((err) => {
        setError(describe(err));
        setMode("login");
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialMode, verifyToken]);

  const go = (next: Mode) => {
    setMode(next);
    setError(null);
    setNotice(null);
  };

  const onSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      if (mode === "login") {
        await auth.login(email, password);
      } else if (mode === "signup") {
        const message = await auth.signup(email, password);
        setNotice(message);
        setPassword("");
        setMode("login");
      } else if (mode === "forgot") {
        await auth.forgotPassword(email);
        setNotice("If that account exists, a reset link is on its way.");
      } else if (mode === "reset" && resetToken) {
        await auth.resetPassword(resetToken, password);
        window.location.href = "/dashboard";
      }
    } catch (err) {
      setError(describe(err));
    } finally {
      setBusy(false);
    }
  };

  const copy = COPY[mode];
  const showEmail = mode !== "reset" && mode !== "verify";
  const showPassword =
    mode === "login" || mode === "signup" || mode === "reset";

  return (
    <div className="aix-auth">
      <aside className="aix-auth__panel">
        <div className="aix-auth__brand">
          <img src="/logo-mark.png" alt="draw.getdraw.app" />
        </div>
        <div className="aix-auth__pitch">
          <h2>
            Think it.
            <br />
            Draw it.
          </h2>
          <p>
            A shared canvas for your whole team — diagrams, whiteboards and
            wireframes, in one place.
          </p>
        </div>
        <div className="aix-auth__panel-footer">
          <span>Real-time collaboration</span>
          <span aria-hidden="true">•</span>
          <span>Your workspace, your data</span>
        </div>
      </aside>

      <main className="aix-auth__stage">
        <form className="aix-auth__card" onSubmit={onSubmit}>
          <img
            className="aix-auth__mark"
            src="/logo-mark.png"
            alt="draw.getdraw.app"
          />
          <h1 className="aix-auth__title">{copy.title}</h1>
          <p className="aix-auth__subtitle">{copy.subtitle}</p>

          {mode === "verify" && !error && (
            <div className="aix-auth__notice">Confirming your address…</div>
          )}

          {showEmail && (
            <label className="aix-auth__field">
              <span>Email address</span>
              <input
                type="email"
                value={email}
                placeholder="Enter your email address"
                autoComplete="email"
                required
                onChange={(e) => setEmail(e.target.value)}
              />
            </label>
          )}

          {showPassword && (
            <label className="aix-auth__field">
              <span>Password</span>
              <input
                type="password"
                value={password}
                placeholder={
                  mode === "login"
                    ? "Enter your password"
                    : "At least 8 characters"
                }
                minLength={8}
                required
                autoComplete={
                  mode === "login" ? "current-password" : "new-password"
                }
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
          )}

          {error && <div className="aix-auth__error">{error}</div>}
          {notice && <div className="aix-auth__notice">{notice}</div>}

          {mode !== "verify" && (
            <button className="aix-auth__submit" type="submit" disabled={busy}>
              {busy ? "Working…" : copy.submit}
            </button>
          )}

          {mode === "login" && (
            <button
              type="button"
              className="aix-auth__inline"
              onClick={() => go("forgot")}
            >
              Forgot password?
            </button>
          )}
        </form>

        {(mode === "login" || mode === "signup") && (
          <p className="aix-auth__switch">
            {mode === "login" ? (
              <>
                Don't have an account?{" "}
                <button type="button" onClick={() => go("signup")}>
                  Sign up
                </button>
              </>
            ) : (
              <>
                Already have an account?{" "}
                <button type="button" onClick={() => go("login")}>
                  Sign in
                </button>
              </>
            )}
          </p>
        )}
        {(mode === "forgot" || mode === "reset") && (
          <p className="aix-auth__switch">
            <button type="button" onClick={() => go("login")}>
              Back to sign in
            </button>
          </p>
        )}
      </main>
    </div>
  );
};
