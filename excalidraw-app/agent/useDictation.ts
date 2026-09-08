import { useCallback, useEffect, useRef, useState } from "react";

type SpeechRecognitionLike = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start: () => void;
  stop: () => void;
  onresult: ((event: any) => void) | null;
  onerror: ((event: any) => void) | null;
  onend: (() => void) | null;
};

const Recognition: (new () => SpeechRecognitionLike) | undefined =
  typeof window !== "undefined"
    ? (window as any).SpeechRecognition ||
      (window as any).webkitSpeechRecognition
    : undefined;

/**
 * Voice input through the browser's own recogniser — nothing is uploaded, and
 * there is no key to configure. Only final results are committed, so the draft
 * doesn't flicker through the interim guesses while someone is mid-sentence.
 */
export const useDictation = (onText: (text: string) => void) => {
  const [listening, setListening] = useState(false);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const callbackRef = useRef(onText);
  callbackRef.current = onText;

  useEffect(() => {
    return () => recognitionRef.current?.stop();
  }, []);

  const toggle = useCallback(() => {
    if (!Recognition) {
      return;
    }
    if (recognitionRef.current) {
      recognitionRef.current.stop();
      recognitionRef.current = null;
      setListening(false);
      return;
    }

    const recognition = new Recognition();
    recognition.continuous = true;
    recognition.interimResults = false;
    recognition.lang = navigator.language || "en-US";

    recognition.onresult = (event: any) => {
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        if (result.isFinal) {
          callbackRef.current(String(result[0].transcript).trim());
        }
      }
    };
    // a denied mic permission or a dropped connection ends the session; the
    // button has to come back up or it looks stuck listening
    recognition.onerror = () => {
      recognitionRef.current = null;
      setListening(false);
    };
    recognition.onend = () => {
      recognitionRef.current = null;
      setListening(false);
    };

    recognition.start();
    recognitionRef.current = recognition;
    setListening(true);
  }, []);

  return { supported: !!Recognition, listening, toggle };
};
