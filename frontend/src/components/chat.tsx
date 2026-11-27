"use client";

import clsx from "clsx";
import { Bot, Mic, MicOff, Send, Wand2 } from "lucide-react";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";

import { useHydrated } from "@/lib/session";
import type { InterviewSession } from "@/lib/types";

import { Button } from "./ui";

const ARABIC = /[؀-ۿ]/;

/* Minimal typing for the Web Speech API (not in TypeScript's DOM lib). */
interface SpeechResultEvent {
  results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }>;
}
interface SpeechRecognizer {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  start(): void;
  stop(): void;
  onresult: ((event: SpeechResultEvent) => void) | null;
  onend: (() => void) | null;
  onerror: (() => void) | null;
}
type SpeechCtor = new () => SpeechRecognizer;

function speechCtor(): SpeechCtor | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as { SpeechRecognition?: SpeechCtor; webkitSpeechRecognition?: SpeechCtor };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export function ChatPanel({
  session,
  onSend,
  sending,
  onDone,
  completing,
  canEdit,
}: {
  session: InterviewSession;
  onSend: (text: string) => Promise<boolean>;
  sending: boolean;
  onDone: () => void;
  completing: boolean;
  canEdit: boolean;
}) {
  const [text, setText] = useState("");
  const [listening, setListening] = useState(false);
  const [voiceLang, setVoiceLang] = useState<"ur-PK" | "en-PK">("ur-PK");
  const recognizer = useRef<SpeechRecognizer | null>(null);
  const listRef = useRef<HTMLOListElement>(null);
  const hydrated = useHydrated();
  const voiceSupported = hydrated && Boolean(speechCtor());
  const answered = session.messages.some((m) => m.sender === "user");
  const open = session.status === "in_progress";

  useEffect(() => {
    // Scroll only the transcript, never the page. (Block body on purpose: an effect must
    // return nothing or a cleanup function.)
    const list = listRef.current;
    if (list) list.scrollTo({ top: list.scrollHeight, behavior: "smooth" });
  }, [session.messages.length, sending]);

  async function send() {
    const value = text.trim();
    if (!value || sending) return;
    if (await onSend(value)) setText("");
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void send();
    }
  }

  function toggleVoice() {
    const Ctor = speechCtor();
    if (!Ctor) return;
    if (listening) {
      recognizer.current?.stop();
      return;
    }
    const rec = new Ctor();
    rec.lang = voiceLang;
    rec.interimResults = false;
    rec.continuous = true;
    rec.onresult = (event) => {
      const transcript = Array.from(event.results)
        .filter((r) => r.isFinal)
        .map((r) => r[0]?.transcript ?? "")
        .join(" ");
      if (transcript) setText((current) => `${current} ${transcript}`.trim());
    };
    rec.onend = () => setListening(false);
    rec.onerror = () => setListening(false);
    recognizer.current = rec;
    rec.start();
    setListening(true);
  }

  return (
    <div className="flex h-[36rem] flex-col rounded-2xl border border-slate-200 bg-white lg:h-[calc(100dvh-13rem)] lg:min-h-[34rem]">
      <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="grid size-8 place-items-center rounded-lg bg-brand-50 text-brand-600">
            <Bot className="size-4" aria-hidden />
          </span>
          <div>
            <div className="text-sm font-semibold text-slate-900">Process interview</div>
            <div className="text-xs text-slate-600">
              Question {Math.min(session.question_count, session.max_questions)} of {session.max_questions} ·
              English, اردو or Roman Urdu
            </div>
          </div>
        </div>
      </div>

      <ol
        ref={listRef}
        className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-4"
        aria-live="polite"
        aria-label="Interview transcript"
      >
        {session.messages.map((message) => {
          const rtl = ARABIC.test(message.content);
          return (
            <li
              key={message.id}
              className={clsx("flex", message.sender === "user" ? "justify-end" : "justify-start")}
            >
              <div
                dir={rtl ? "rtl" : undefined}
                className={clsx(
                  "max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-sm",
                  rtl && "urdu",
                  message.sender === "user"
                    ? "rounded-br-md bg-brand-600 text-white"
                    : "rounded-bl-md bg-slate-100 text-slate-900",
                  message.meta_json?.kind === "clarification" && "ring-2 ring-amber-300",
                )}
              >
                {message.content}
              </div>
            </li>
          );
        })}
        {sending ? (
          <li className="flex justify-start">
            <div className="rounded-2xl rounded-bl-md bg-slate-100 px-4 py-3 text-sm text-slate-600">
              <span className="inline-flex gap-1" aria-label="AI is typing">
                <span className="size-1.5 animate-bounce rounded-full bg-slate-400" />
                <span className="size-1.5 animate-bounce rounded-full bg-slate-400 [animation-delay:150ms]" />
                <span className="size-1.5 animate-bounce rounded-full bg-slate-400 [animation-delay:300ms]" />
              </span>
            </div>
          </li>
        ) : null}
      </ol>

      {open && canEdit ? (
        <div className="border-t border-slate-100 p-3">
          {session.ready_for_mapping ? (
            <div className="mb-3 rounded-xl bg-saved-50 px-3 py-2 text-sm text-saved-700">
              I have enough detail. You can add more, or draw the map now.
            </div>
          ) : null}
          <div className="flex items-end gap-2">
            <label className="sr-only" htmlFor="answer">
              Your answer
            </label>
            <textarea
              id="answer"
              rows={2}
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder="Type your answer… (Enter to send)"
              className="min-h-11 flex-1 resize-none rounded-xl border border-slate-300 px-3 py-2.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-200"
              disabled={sending}
            />
            {voiceSupported ? (
              <button
                type="button"
                onClick={toggleVoice}
                className={clsx(
                  "grid size-11 place-items-center rounded-xl border",
                  listening
                    ? "border-red-300 bg-red-50 text-red-600"
                    : "border-slate-300 text-slate-600 hover:bg-slate-50",
                )}
                aria-pressed={listening}
                aria-label={
                  listening
                    ? "Stop voice input"
                    : `Speak your answer (${voiceLang === "ur-PK" ? "Urdu" : "English"})`
                }
                onContextMenu={(e) => {
                  e.preventDefault();
                  setVoiceLang((l) => (l === "ur-PK" ? "en-PK" : "ur-PK"));
                }}
              >
                {listening ? <MicOff className="size-5" /> : <Mic className="size-5" />}
              </button>
            ) : null}
            <Button
              onClick={send}
              loading={sending}
              disabled={!text.trim()}
              aria-label="Send answer"
              icon={<Send className="size-4" />}
            />
          </div>
          <div className="mt-3 flex items-center justify-between gap-3">
            <span className="text-xs text-slate-600">
              {voiceSupported
                ? `Voice: ${voiceLang === "ur-PK" ? "Urdu" : "English"} (right-click the mic to switch)`
                : ""}
            </span>
            <Button
              variant={session.ready_for_mapping ? "success" : "secondary"}
              icon={<Wand2 className="size-4" />}
              onClick={onDone}
              loading={completing}
              disabled={!answered}
            >
              Done — draw my map
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
