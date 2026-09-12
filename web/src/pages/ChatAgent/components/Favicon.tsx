import React, { useState } from 'react';
import { isPublicHost, faviconUrlForHost } from './faviconUtils';

/**
 * Circular monogram fallback shown when a favicon fails to load (or no
 * domain is available). Renders the first character of the label.
 */
export function Monogram({ letter, size = 14 }: { letter: string; size?: number }): React.ReactElement {
  return (
    <span
      style={{
        width: size,
        height: size,
        borderRadius: size / 2,
        background: 'var(--color-bg-surface)',
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontSize: size * 0.65,
        fontWeight: 600,
        color: 'var(--color-text-secondary)',
        flexShrink: 0,
        textTransform: 'uppercase',
      }}
    >
      {letter}
    </span>
  );
}

/**
 * Favicon for a domain, fetched directly from the host itself
 * (``https://<domain>/favicon.ico``) — no third-party icon service, so it
 * works from mainland China where Google's s2 favicon endpoint is
 * unreachable. Falls back to a {@link Monogram} of the domain's first
 * character when the image fails, the domain is empty, or the host is
 * non-public (never probed at all).
 */
export function Favicon({ domain, size = 14 }: { domain: string; size?: number }): React.ReactElement {
  const [failed, setFailed] = useState(false);

  if (failed || !domain || !isPublicHost(domain)) {
    return <Monogram letter={domain.charAt(0) || '?'} size={size} />;
  }

  const src = faviconUrlForHost(domain);
  if (!src) {
    return <Monogram letter={domain.charAt(0) || '?'} size={size} />;
  }

  return (
    <img
      src={src}
      alt=""
      width={size}
      height={size}
      loading="lazy"
      decoding="async"
      style={{ borderRadius: size > 14 ? 3 : 2, flexShrink: 0 }}
      onError={() => setFailed(true)}
    />
  );
}
