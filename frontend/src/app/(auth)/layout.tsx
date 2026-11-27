import { CheckCircle2 } from "lucide-react";
import type { ReactNode } from "react";

import { Wordmark } from "@/components/logo";

const POINTS = [
  "Describe your process in English, Urdu or Roman Urdu",
  "See which tasks eat your week and what to automate first",
  "Approve AI replies and big orders from your phone",
];

export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="grid min-h-dvh lg:grid-cols-[1.1fr_1fr]">
      <section className="relative hidden overflow-hidden bg-brand-700 p-12 text-white lg:flex lg:flex-col lg:justify-between">
        <div className="absolute -right-24 -top-24 size-96 rounded-full bg-brand-600/60" aria-hidden />
        <div className="absolute -bottom-32 -left-16 size-96 rounded-full bg-brand-800/60" aria-hidden />
        <div className="relative rounded-xl bg-white/95 px-3 py-2 self-start">
          <Wordmark />
        </div>
        <div className="relative max-w-lg">
          <h1 className="text-4xl font-bold leading-tight">Tell IntelliFlow how your business runs.</h1>
          <p className="mt-3 text-lg text-brand-100">
            It shows you what to automate, then automates it — safely, with you in control.
          </p>
          <ul className="mt-8 space-y-3">
            {POINTS.map((point) => (
              <li key={point} className="flex items-start gap-3 text-brand-50">
                <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-emerald-300" aria-hidden />
                {point}
              </li>
            ))}
          </ul>
        </div>
        <p className="relative text-sm text-brand-200">
          Built for WhatsApp-first small businesses in Pakistan.
        </p>
      </section>
      <section className="flex flex-col items-center justify-center px-4 py-10 sm:px-8">
        <div className="mb-8 lg:hidden">
          <Wordmark />
        </div>
        <div className="w-full max-w-md">{children}</div>
      </section>
    </div>
  );
}
