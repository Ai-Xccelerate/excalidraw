import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import {
  changePassword as apiChangePassword,
  forgotPassword as apiForgotPassword,
  getMe,
  login as apiLogin,
  resetPassword as apiResetPassword,
  signup as apiSignup,
  verifyEmail as apiVerifyEmail,
  clearStoredToken,
  getStoredToken,
  setActiveWorkspaceId,
  setStoredToken,
  SESSION_EXPIRED_EVENT,
  type AuthUser,
} from "../data/backend";

type AuthState = {
  user: AuthUser | null;
  isLoaded: boolean;
  isSignedIn: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (
    email: string,
    password: string,
    username?: string,
  ) => Promise<string>;
  verifyEmail: (token: string) => Promise<void>;
  logout: () => void;
  forgotPassword: (email: string) => Promise<void>;
  resetPassword: (token: string, password: string) => Promise<void>;
  changePassword: (current: string, next: string) => Promise<void>;
  /** re-reads the account after it changes elsewhere (e.g. Settings) */
  refreshUser: () => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

export const AuthProvider = ({ children }: { children: React.ReactNode }) => {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoaded, setIsLoaded] = useState(false);

  // a stored token is only a claim; confirm it against /me before treating the
  // session as valid, so an expired or revoked token lands on the sign-in
  // screen instead of a half-signed-in app that 401s on every request
  useEffect(() => {
    let cancelled = false;
    const restore = async () => {
      if (!getStoredToken()) {
        setIsLoaded(true);
        return;
      }
      try {
        const me = await getMe();
        if (!cancelled) {
          setUser(me);
        }
      } catch {
        clearStoredToken();
      } finally {
        if (!cancelled) {
          setIsLoaded(true);
        }
      }
    };
    restore();
    return () => {
      cancelled = true;
    };
  }, []);

  // a rejected token means this session is over; drop the user so the app
  // stops rendering signed-in chrome and routes back to sign-in
  useEffect(() => {
    const onExpired = () => setUser(null);
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const session = await apiLogin(email, password);
    setStoredToken(session.token);
    setUser(session.user);
  }, []);

  const signup = useCallback(
    async (email: string, password: string, username?: string) => {
      const result = await apiSignup(email, password, username);
      return result.message;
    },
    [],
  );

  const changePassword = useCallback(async (current: string, next: string) => {
    const result = await apiChangePassword(current, next);
    // the old token died with the old password; adopt the replacement so the
    // user isn't signed out of the tab they just changed it in
    setStoredToken(result.token);
  }, []);

  const verifyEmail = useCallback(async (token: string) => {
    const session = await apiVerifyEmail(token);
    setStoredToken(session.token);
    setUser(session.user);
  }, []);

  const logout = useCallback(() => {
    clearStoredToken();
    setActiveWorkspaceId(null);
    setUser(null);
    window.location.href = "/";
  }, []);

  const refreshUser = useCallback(async () => {
    if (!getStoredToken()) {
      return;
    }
    try {
      setUser(await getMe());
    } catch {
      // a failed refresh is not worth signing the user out over; the next
      // request that actually matters will surface the expiry
    }
  }, []);

  const resetPassword = useCallback(async (token: string, password: string) => {
    const session = await apiResetPassword(token, password);
    setStoredToken(session.token);
    setUser(session.user);
  }, []);

  const value = useMemo(
    () => ({
      user,
      isLoaded,
      isSignedIn: user !== null,
      login,
      signup,
      verifyEmail,
      logout,
      forgotPassword: apiForgotPassword,
      resetPassword,
      changePassword,
      refreshUser,
    }),
    [
      user,
      isLoaded,
      login,
      signup,
      verifyEmail,
      logout,
      resetPassword,
      changePassword,
      refreshUser,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = (): AuthState => {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used inside <AuthProvider>");
  }
  return ctx;
};

/** Drop-in replacements for the Clerk components of the same name. Both render
 * nothing until the stored session has been checked, so the UI never flickers
 * from signed-out to signed-in on a reload. */
export const SignedIn = ({ children }: { children: React.ReactNode }) => {
  const { isLoaded, isSignedIn } = useAuth();
  return isLoaded && isSignedIn ? <>{children}</> : null;
};

export const SignedOut = ({ children }: { children: React.ReactNode }) => {
  const { isLoaded, isSignedIn } = useAuth();
  return isLoaded && !isSignedIn ? <>{children}</> : null;
};
