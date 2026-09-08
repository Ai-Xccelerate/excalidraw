import { useRef, useState } from "react";

import { copyTextToSystemClipboard } from "../clipboard";
import { useCopyStatus } from "../hooks/useCopiedIndicator";
import { useI18n } from "../i18n";

import { Dialog } from "./Dialog";
import { FilledButton } from "./FilledButton";
import { TextField } from "./TextField";
import { copyIcon, share, shareIOS, shareWindows } from "./icons";

import "./ShareableLinkDialog.scss";

const getShareIcon = () => {
  const navigator = window.navigator as any;
  if (/Apple/.test(navigator.vendor)) {
    return shareIOS;
  }
  return navigator.appVersion.indexOf("Win") !== -1 ? shareWindows : share;
};

export type ShareableLinkDialogProps = {
  link: string;

  onCloseRequest: () => void;
  setErrorMessage: (error: string) => void;
};

export const ShareableLinkDialog = ({
  link,
  onCloseRequest,
  setErrorMessage,
}: ShareableLinkDialogProps) => {
  const { t } = useI18n();
  const [, setJustCopied] = useState(false);
  const timerRef = useRef<number>(0);
  const ref = useRef<HTMLInputElement>(null);

  const copyRoomLink = async () => {
    try {
      await copyTextToSystemClipboard(link);
    } catch (e) {
      setErrorMessage(t("errors.copyToSystemClipboardFailed"));
    }
    setJustCopied(true);

    if (timerRef.current) {
      window.clearTimeout(timerRef.current);
    }

    timerRef.current = window.setTimeout(() => {
      setJustCopied(false);
    }, 3000);

    ref.current?.select();
  };
  const { onCopy, copyStatus } = useCopyStatus();

  // on a phone, copying the link is only half the job — hand it to the share
  // sheet so it can go straight into a message
  const isShareSupported = "share" in navigator;
  const shareLink = async () => {
    try {
      await navigator.share({ title: "Excalidraw", text: link, url: link });
    } catch (error: any) {
      // the visitor dismissed the share sheet
    }
  };

  return (
    <Dialog onCloseRequest={onCloseRequest} title={false} size="small">
      <div className="ShareableLinkDialog">
        <h3>Shareable link</h3>
        <div className="ShareableLinkDialog__linkRow">
          <TextField
            ref={ref}
            label="Link"
            readonly
            fullWidth
            value={link}
            selectOnRender
          />
          {isShareSupported && (
            <FilledButton
              size="large"
              variant="icon"
              label={t("labels.share")}
              icon={getShareIcon()}
              onClick={shareLink}
            />
          )}
          <FilledButton
            size="large"
            label={t("buttons.copyLink")}
            icon={copyIcon}
            status={copyStatus}
            onClick={() => {
              onCopy();
              copyRoomLink();
            }}
          />
        </div>
        <div className="ShareableLinkDialog__description">
          🔒 {t("alerts.uploadedSecurly")}
        </div>
      </div>
    </Dialog>
  );
};
