// 3D, schematic and PCB viewers. The 3D model viewer lives in `@kehora/viewer/model` (lazy-load
// it: it pulls in three.js); this entry stays light for the placeholder.

export interface ViewerPlaceholderProps {
  title?: string;
  hint?: string;
}

export function ViewerPlaceholder({
  title = "Viewer",
  hint = "Your model will appear here once the build produces one.",
}: ViewerPlaceholderProps) {
  return (
    <div
      role="img"
      aria-label={`${title}: ${hint}`}
      className="flex h-full min-h-64 flex-col items-center justify-center gap-3 rounded-lg border border-dashed p-8 text-center"
    >
      <svg viewBox="0 0 64 64" className="size-16 text-muted-foreground" aria-hidden="true">
        <path
          d="M32 6 56 19v26L32 58 8 45V19Z M8 19l24 13 24-13 M32 32v26"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinejoin="round"
        />
      </svg>
      <p className="text-sm font-medium">{title}</p>
      <p className="max-w-xs text-sm text-muted-foreground">{hint}</p>
    </div>
  );
}
