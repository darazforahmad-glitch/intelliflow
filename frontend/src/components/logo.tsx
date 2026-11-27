export function Logo({ className = "size-8" }: { className?: string }) {
  return (
    <svg viewBox="0 0 64 64" className={className} aria-hidden>
      <rect width="64" height="64" rx="14" fill="#4f46e5" />
      <path
        d="M17 23 L32 43 L47 23"
        fill="none"
        stroke="#fff"
        strokeWidth="4.5"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      <circle cx="17" cy="23" r="6.5" fill="#fff" />
      <circle cx="47" cy="23" r="6.5" fill="#fff" />
      <circle cx="32" cy="43" r="6.5" fill="#10b981" stroke="#fff" strokeWidth="2.5" />
    </svg>
  );
}

export function Wordmark() {
  return (
    <span className="flex items-center gap-2">
      <Logo />
      <span className="text-lg font-bold tracking-tight text-slate-900">IntelliFlow</span>
    </span>
  );
}
