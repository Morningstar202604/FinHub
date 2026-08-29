/**
 * Our own mark, drawn rather than fetched.
 *
 * A stylized yuan sign (¥) for 财枢 FinHub — inline and stroked in
 * `currentColor` so it takes the tint of whatever tile it sits in: the same
 * mark reads on a light bed and a dark one without a second asset, and it
 * cannot drift from the theme the way a pair of theme-picked files does. The
 * favicons keep their own opaque beds because a browser tab has no surface to
 * inherit; a tile in a list does.
 */
export function LangAlphaMark({ className = '' }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 56 56"
      fill="none"
      stroke="currentColor"
      strokeWidth={3.2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      className={className}
    >
      <path d="M16 13 L28 30 L40 13" />
      <path d="M28 30 V46" />
      <path d="M19 36 H37" />
      <path d="M19 42 H37" />
    </svg>
  );
}
