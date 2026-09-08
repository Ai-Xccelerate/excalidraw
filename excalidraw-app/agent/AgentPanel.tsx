import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { askCanvasAgent } from "../data/backend";

import { applyAgentOperations } from "./applyOperations";
import { useDictation } from "./useDictation";

import "./AgentPanel.scss";

import type { AgentOperations, AgentTurn } from "../data/backend";

import type { ExcalidrawImperativeAPI } from "@excalidraw/excalidraw/types";

type Entry = AgentTurn & {
  /** what the agent did to the canvas on this turn, for the receipt line */
  did?: AgentOperations["summary"];
  failed?: boolean;
};

type Attachment = { name: string; text: string };

const GREETING =
  "Tell me what you want to show and I'll draw it. I can see the board — " +
  "select something first if you want me to work on just that part.";

const READABLE_TEXT = /\.(txt|md|markdown|csv|json|ya?ml|tsv|log)$/i;
const MAX_ATTACHMENT_CHARS = 20000;

const receipt = (did: AgentOperations["summary"]): string => {
  const parts: string[] = [];
  if (did.created) {
    parts.push(`${did.created} shape${did.created === 1 ? "" : "s"}`);
  }
  if (did.connected) {
    parts.push(`${did.connected} connection${did.connected === 1 ? "" : "s"}`);
  }
  if (did.updated) {
    parts.push(`${did.updated} changed`);
  }
  if (did.deleted) {
    parts.push(`${did.deleted} removed`);
  }
  return parts.length ? `Drew ${parts.join(" · ")}` : "";
};

export const AgentPanel = ({
  excalidrawAPI,
  onClose,
}: {
  excalidrawAPI: ExcalidrawImperativeAPI;
  onClose: () => void;
}) => {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [draft, setDraft] = useState("");
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [images, setImages] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedCount, setSelectedCount] = useState(0);
  const [elementCount, setElementCount] = useState(0);

  const transcriptRef = useRef<HTMLDivElement>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const dictation = useDictation((text) =>
    setDraft((current) => (current ? `${current} ${text}` : text)),
  );

  // the status line has to track the canvas, not the last send: the user
  // selects things while reading the reply
  useEffect(() => {
    const read = () => {
      const state = excalidrawAPI.getAppState();
      const live = excalidrawAPI
        .getSceneElements()
        .filter((element) => !element.isDeleted);
      setElementCount(live.length);
      setSelectedCount(
        live.filter((element) => state.selectedElementIds[element.id]).length,
      );
    };
    read();
    return excalidrawAPI.onChange(read);
  }, [excalidrawAPI]);

  useEffect(() => {
    transcriptRef.current?.scrollTo({
      top: transcriptRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [entries, busy]);

  const boardState = useCallback(() => {
    const state = excalidrawAPI.getAppState();
    const elements = excalidrawAPI
      .getSceneElements()
      .filter((element) => !element.isDeleted);

    return {
      // only what the agent can reason about — the full element carries
      // points, seeds and version noise it has no use for
      elements: elements.map((element) => ({
        id: element.id,
        type: element.type,
        x: Math.round(element.x),
        y: Math.round(element.y),
        width: Math.round(element.width),
        height: Math.round(element.height),
        backgroundColor: element.backgroundColor,
        strokeColor: element.strokeColor,
        text: (element as any).text,
        containerId: (element as any).containerId,
        startBinding: (element as any).startBinding
          ? { elementId: (element as any).startBinding.elementId }
          : undefined,
        endBinding: (element as any).endBinding
          ? { elementId: (element as any).endBinding.elementId }
          : undefined,
      })),
      selected_ids: elements
        .filter((element) => state.selectedElementIds[element.id])
        .map((element) => element.id),
    };
  }, [excalidrawAPI]);

  const send = async () => {
    const text = draft.trim();
    if ((!text && !images.length) || busy) {
      return;
    }

    const outgoing: Entry = { role: "user", content: text, images };
    const history = [...entries, outgoing];

    setEntries(history);
    setDraft("");
    setImages([]);
    setBusy(true);
    setError(null);

    try {
      const { reply, operations } = await askCanvasAgent({
        messages: history.map(({ role, content, images: sent }) => ({
          role,
          content,
          images: sent,
        })),
        board: boardState(),
        attachments,
      });

      let did: AgentOperations["summary"] | undefined;
      if (operations) {
        const created = applyAgentOperations(excalidrawAPI, operations);
        did = operations.summary;
        if (created.length) {
          // land on what it just drew, so the next instruction has a subject
          excalidrawAPI.updateScene({
            appState: {
              selectedElementIds: Object.fromEntries(
                created.map((id) => [id, true]),
              ),
            },
          });
          excalidrawAPI.scrollToContent(
            excalidrawAPI
              .getSceneElements()
              .filter((element) => created.includes(element.id)),
            { fitToViewport: false, animate: true },
          );
        }
        // an attachment is context for the request that used it
        setAttachments([]);
      }

      setEntries([...history, { role: "assistant", content: reply, did }]);
    } catch (err: any) {
      setError(err?.message || "The agent could not be reached.");
      setEntries([
        ...history,
        {
          role: "assistant",
          content: "I couldn't finish that one. Try again?",
          failed: true,
        },
      ]);
    } finally {
      setBusy(false);
      composerRef.current?.focus();
    }
  };

  const attach = async (files: FileList | null) => {
    if (!files?.length) {
      return;
    }
    const nextFiles: Attachment[] = [];
    const nextImages: string[] = [];

    for (const file of Array.from(files).slice(0, 4)) {
      if (file.type.startsWith("image/")) {
        nextImages.push(
          await new Promise<string>((resolve) => {
            const reader = new FileReader();
            reader.onload = () => resolve(String(reader.result));
            reader.readAsDataURL(file);
          }),
        );
      } else if (
        READABLE_TEXT.test(file.name) ||
        file.type.startsWith("text/")
      ) {
        const text = await file.text();
        nextFiles.push({
          name: file.name,
          text: text.slice(0, MAX_ATTACHMENT_CHARS),
        });
      } else {
        // a PDF or a docx would arrive as bytes the model can't read; say so
        // rather than attaching something that silently contributes nothing
        setError(
          `${file.name} isn't a format I can read — try text or an image.`,
        );
      }
    }
    setAttachments((current) => [...current, ...nextFiles]);
    setImages((current) => [...current, ...nextImages]);
  };

  const status = useMemo(() => {
    if (busy) {
      return "Thinking…";
    }
    if (selectedCount) {
      return `Working on ${selectedCount} selected object${
        selectedCount === 1 ? "" : "s"
      }`;
    }
    return elementCount
      ? `Whole board · ${elementCount} objects`
      : "Empty board";
  }, [busy, selectedCount, elementCount]);

  return (
    <aside className="aix-agent" aria-label="Canvas assistant">
      <header className="aix-agent__head">
        <span className="aix-agent__title">Canvas assistant</span>
        <button
          className="aix-agent__close"
          onClick={onClose}
          aria-label="Close assistant"
        >
          ✕
        </button>
      </header>

      <div className="aix-agent__transcript" ref={transcriptRef}>
        {entries.length === 0 && (
          <p className="aix-agent__greeting">{GREETING}</p>
        )}

        {entries.map((entry, index) => (
          <div
            key={index}
            className={`aix-agent__turn aix-agent__turn--${entry.role}${
              entry.failed ? " aix-agent__turn--failed" : ""
            }`}
          >
            {entry.content && <p>{entry.content}</p>}
            {!!entry.images?.length && (
              <div className="aix-agent__thumbs">
                {entry.images.map((image, i) => (
                  <img key={i} src={image} alt="" />
                ))}
              </div>
            )}
            {entry.did && receipt(entry.did) && (
              <span className="aix-agent__receipt">{receipt(entry.did)}</span>
            )}
          </div>
        ))}

        {busy && (
          <div className="aix-agent__turn aix-agent__turn--assistant aix-agent__thinking">
            <span />
            <span />
            <span />
          </div>
        )}
      </div>

      {error && (
        <div className="aix-agent__error" onClick={() => setError(null)}>
          {error}
        </div>
      )}

      {(attachments.length > 0 || images.length > 0) && (
        <div className="aix-agent__attachments">
          {attachments.map((attachment) => (
            <span key={attachment.name} className="aix-agent__chip">
              {attachment.name}
              <button
                onClick={() =>
                  setAttachments((current) =>
                    current.filter((item) => item.name !== attachment.name),
                  )
                }
                aria-label={`Remove ${attachment.name}`}
              >
                ✕
              </button>
            </span>
          ))}
          {images.map((image, index) => (
            <span key={index} className="aix-agent__chip">
              image {index + 1}
              <button
                onClick={() =>
                  setImages((current) => current.filter((_, i) => i !== index))
                }
                aria-label="Remove image"
              >
                ✕
              </button>
            </span>
          ))}
        </div>
      )}

      <div className="aix-agent__status">
        <span className="aix-agent__dot" />
        {status}
      </div>

      <div className="aix-agent__composer">
        <button
          className="aix-agent__icon"
          onClick={() => fileRef.current?.click()}
          title="Attach a document or image"
          aria-label="Attach a document or image"
        >
          📎
        </button>
        <input
          ref={fileRef}
          type="file"
          multiple
          hidden
          onChange={(event) => {
            attach(event.target.files);
            event.target.value = "";
          }}
        />

        <textarea
          ref={composerRef}
          className="aix-agent__input"
          value={draft}
          placeholder="What shall we draw?"
          rows={1}
          onChange={(event) => setDraft(event.target.value)}
          onPaste={(event) => {
            const files = Array.from(event.clipboardData.files);
            if (files.length) {
              event.preventDefault();
              attach(event.clipboardData.files);
            }
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              send();
            }
          }}
        />

        {dictation.supported && (
          <button
            className={`aix-agent__icon${
              dictation.listening ? " aix-agent__icon--live" : ""
            }`}
            onClick={dictation.toggle}
            title={dictation.listening ? "Stop dictating" : "Dictate"}
            aria-label={dictation.listening ? "Stop dictating" : "Dictate"}
          >
            🎙
          </button>
        )}

        <button
          className="aix-agent__send"
          onClick={send}
          disabled={busy || (!draft.trim() && !images.length)}
          aria-label="Send"
        >
          ↑
        </button>
      </div>
    </aside>
  );
};
