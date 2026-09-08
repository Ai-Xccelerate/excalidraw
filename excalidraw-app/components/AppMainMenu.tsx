import {
  loginIcon,
  eyeIcon,
  PlusIcon,
  share,
  TrashIcon,
} from "@excalidraw/excalidraw/components/icons";
import { t } from "@excalidraw/excalidraw/i18n";
import { MainMenu } from "@excalidraw/excalidraw/index";
import React from "react";

import { isDevEnv } from "@excalidraw/common";

import type { Theme } from "@excalidraw/element/types";

import { SignedIn, SignedOut, useAuth } from "../auth/AuthContext";

import { useAtomValue } from "../app-jotai";
import {
  createDrawing,
  currentDrawingIdAtom,
  deleteDrawing,
} from "../data/backend";
import { LanguageList } from "../app-language/LanguageList";

import { saveDebugState } from "./DebugCanvas";

import "./AppMainMenu.scss";

/** first-party email + password auth is always available */
const AUTH_ENABLED = true;

const handleNewDrawing = async () => {
  try {
    const drawing = await createDrawing();
    window.location.assign(`/d/${drawing.id}`);
  } catch (error) {
    console.error("failed to create drawing", error);
  }
};

const handleDeleteDrawing = async (drawingId: string) => {
  // eslint-disable-next-line no-alert
  if (!window.confirm("Delete this drawing? This can't be undone.")) {
    return;
  }
  try {
    await deleteDrawing(drawingId);
    window.location.assign("/dashboard");
  } catch (error) {
    console.error("failed to delete drawing", error);
  }
};

export const AppMainMenu: React.FC<{
  onShareDialogOpen: () => any;
  onCollabDialogOpen: () => any;
  isCollaborating: boolean;
  isCollabEnabled: boolean;
  theme: Theme | "system";
  refresh: () => void;
}> = React.memo((props) => {
  const currentDrawingId = useAtomValue(currentDrawingIdAtom);
  return (
    <MainMenu>
      <MainMenu.DefaultItems.LoadScene />
      <MainMenu.DefaultItems.SaveToActiveFile />
      <MainMenu.DefaultItems.Export />
      <MainMenu.DefaultItems.SaveAsImage />
      {/* the share dialog is otherwise only reachable from the top-right
          trigger, which mobile doesn't render */}
      <MainMenu.Item icon={share} onSelect={() => props.onShareDialogOpen()}>
        {t("labels.share")}
      </MainMenu.Item>
      {props.isCollabEnabled && (
        <MainMenu.DefaultItems.LiveCollaborationTrigger
          isCollaborating={props.isCollaborating}
          onSelect={() => props.onCollabDialogOpen()}
        />
      )}
      <MainMenu.DefaultItems.CommandPalette className="highlighted" />
      <MainMenu.DefaultItems.SearchMenu />
      <MainMenu.DefaultItems.Help />
      <MainMenu.DefaultItems.ClearCanvas />
      <MainMenu.Separator />
      {AUTH_ENABLED && (
        <>
          <SignedIn>
            <MainMenu.Item
              icon={loginIcon}
              onSelect={() => window.location.assign("/dashboard")}
            >
              Dashboard
            </MainMenu.Item>
            <MainMenu.Item icon={PlusIcon} onSelect={handleNewDrawing}>
              New drawing
            </MainMenu.Item>
            {currentDrawingId && (
              <MainMenu.Item
                icon={TrashIcon}
                onSelect={() => handleDeleteDrawing(currentDrawingId)}
              >
                Delete drawing
              </MainMenu.Item>
            )}
            <MainMenu.ItemCustom>
              <AccountMenuItem />
            </MainMenu.ItemCustom>
          </SignedIn>
          <SignedOut>
            <MainMenu.ItemCustom>
              <button
                className="aix-sign-in-button"
                onClick={() => {
                  window.location.href = "/login";
                }}
              >
                Sign in
              </button>
            </MainMenu.ItemCustom>
          </SignedOut>
        </>
      )}
      {isDevEnv() && (
        <MainMenu.Item
          icon={eyeIcon}
          onSelect={() => {
            if (window.visualDebug) {
              delete window.visualDebug;
              saveDebugState({ enabled: false });
            } else {
              window.visualDebug = { data: [] };
              saveDebugState({ enabled: true });
            }
            props?.refresh();
          }}
        >
          Visual Debug
        </MainMenu.Item>
      )}
      <MainMenu.Separator />
      <MainMenu.DefaultItems.Preferences />
      <MainMenu.DefaultItems.ToggleTheme allowSystemTheme theme={props.theme} />
      <MainMenu.ItemCustom>
        <LanguageList style={{ width: "100%" }} />
      </MainMenu.ItemCustom>
      <MainMenu.DefaultItems.ChangeCanvasBackground />
    </MainMenu>
  );
});

const AccountMenuItem = () => {
  const { user, logout } = useAuth();
  return (
    <div className="aix-account-menu">
      <div className="aix-account-menu__identity">
        <span className="aix-account-menu__label">Signed in as</span>
        <span className="aix-account-menu__email" title={user?.email}>
          {user?.email}
        </span>
      </div>
      <button className="aix-sign-in-button" onClick={logout}>
        Sign out
      </button>
    </div>
  );
};
