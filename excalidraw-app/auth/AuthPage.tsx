import React, { useState } from "react";

import { useAuth } from "./AuthContext";

import "./AuthPage.scss";

type Mode = "login" | "signup" | "forgot" | "reset";

const describe = (error: unknown): string =>
  error instanceof Error ? error.message : "Something went wrong. Try again.";

export const AuthPage = ({
  initialMode = "login",
  resetToken = null,
}: {
  initialMode?: Mode;
  resetToken?: string | null;
}) => {
  const auth = useAuth();
  const [mode, setMode] = useState<Mode>(initialMode);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

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
        await auth.signup(email, password);
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

  const title = {
    login: "Sign in",
    signup: "Create your account",
    forgot: "Reset your password",
    reset: "Choose a new password",
  }[mode];

  const submitLabel = {
    login: "Sign in",
    signup: "Create account",
    forgot: "Send reset link",
    reset: "Set new password",
  }[mode];

  return (
    <div className="aix-auth">
      <form className="aix-auth__card" onSubmit={onSubmit}>
        <h1 className="aix-auth__title">{title}</h1>

        {mode !== "reset" && (
          <label className="aix-auth__field">
            <span>Email</span>
            <input
              type="email"
              value={email}
              autoComplete="email"
              required
              onChange={(e) => setEmail(e.target.value)}
            />
          </label>
        )}

        {mode !== "forgot" && (
          <label className="aix-auth__field">
            <span>Password</span>
            <input
              type="password"
              value={password}
              minLength={8}
              required
              autoComplete={
                mode === "login" ? "current-password" : "new-password"
              }
              onChange={(e) => setPassword(e.target.value)}
            />
            {mode !== "login" && (
              <small className="aix-auth__hint">At least 8 characters.</small>
            )}
          </label>
        )}

        {error && <div className="aix-auth__error">{error}</div>}
        {notice && <div className="aix-auth__notice">{notice}</div>}

        <button className="aix-auth__submit" type="submit" disabled={busy}>
          {busy ? "Working…" : submitLabel}
        </button>

        <div className="aix-auth__links">
          {mode === "login" && (
            <>
              <button type="button" onClick={() => go("signup")}>
                Create an account
              </button>
              <button type="button" onClick={() => go("forgot")}>
                Forgot password?
              </button>
            </>
          )}
          {(mode === "signup" || mode === "forgot") && (
            <button type="button" onClick={() => go("login")}>
              Back to sign in
            </button>
          )}
        </div>
      </form>
    </div>
  );
};
