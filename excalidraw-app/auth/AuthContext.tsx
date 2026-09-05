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
  clearStoredToken,
  getStoredToken,
  setActiveWorkspaceId,
  setStoredToken,
  type AuthUser,
} from "../data/backend";

type AuthState = {
  user: AuthUser | null;
  isLoaded: boolean;
  isSignedIn: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string, username?: string) => Promise<void>;
  logout: () => void;
  forgotPassword: (email: string) => Promise<void>;
  resetPassword: (token: string, password: string) => Promise<void>;
  changePassword: (current: string, next: string) => Promise<void>;
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

  const login = useCallback(async (email: string, password: string) => {
    const session = await apiLogin(email, password);
    setStoredToken(session.token);
    setUser(session.user);
  }, []);

  const signup = useCallback(
    async (email: string, password: string, username?: string) => {
      const session = await apiSignup(email, password, username);
      setStoredToken(session.token);
      setUser(session.user);
    },
    [],
  );

  const logout = useCallback(() => {
    clearStoredToken();
    setActiveWorkspaceId(null);
    setUser(null);
    window.location.href = "/";
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
      logout,
      forgotPassword: apiForgotPassword,
      resetPassword,
      changePassword: apiChangePassword,
    }),
    [user, isLoaded, login, signup, logout, resetPassword],
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
