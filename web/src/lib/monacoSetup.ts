/**
 * Pin @monaco-editor/react to the locally bundled monaco instead of its
 * default jsdelivr CDN loader.
 *
 * Without this, the editor silently depends on https://cdn.jsdelivr.net being
 * reachable at runtime — which breaks every self-hosted / air-gapped /
 * firewalled deployment the moment a user opens a file, and makes the app
 * non-deterministic on the open internet too.
 *
 * Loaded from `viewers/CodeEditor.tsx`, NOT from the entry: `CodeEditor` is
 * behind `React.lazy` in both FilePanel callers, so monaco stays off the
 * critical path. It used to be a bare side-effect import in main.tsx, which
 * pulled the full ~4 MB editor into the entry chunk and put every visitor —
 * including the login page — 1.2 MB gzipped away from first paint.
 *
 * `loadMonaco()` is idempotent and awaited by the caller before any <Editor>
 * mounts; `loader.config` must run exactly once, and only before first use.
 *
 * `monaco-editor` is a runtime dependency (it is a bare import resolved at
 * build time and emitted into this chunk, never fetched from the network).
 */
import { loader } from '@monaco-editor/react';
import type * as Monaco from 'monaco-editor';

// Workers must be wired up explicitly under Vite; without them monaco falls
// back to the main thread and the first keystroke blocks rendering.
import editorWorker from 'monaco-editor/esm/vs/editor/editor.worker?worker';
import jsonWorker from 'monaco-editor/esm/vs/language/json/json.worker?worker';
import cssWorker from 'monaco-editor/esm/vs/language/css/css.worker?worker';
import htmlWorker from 'monaco-editor/esm/vs/language/html/html.worker?worker';
import tsWorker from 'monaco-editor/esm/vs/language/typescript/ts.worker?worker';

declare global {
  interface Window {
    MonacoEnvironment?: {
      getWorker: (moduleId: string, label: string) => Worker;
    };
  }
}

let setupPromise: Promise<typeof Monaco> | null = null;

/**
 * Register the bundled monaco with @monaco-editor/react's loader.
 *
 * Resolves once `loader.config` has run, so the caller can await it before
 * rendering the first <Editor>. Concurrent callers share one promise.
 */
export function loadMonaco(): Promise<typeof Monaco> {
  if (setupPromise) return setupPromise;

  setupPromise = import('monaco-editor').then((monaco) => {
    self.MonacoEnvironment = {
      getWorker(_moduleId: string, label: string) {
        switch (label) {
          case 'json':
            return new jsonWorker();
          case 'css':
          case 'scss':
          case 'less':
            return new cssWorker();
          case 'html':
          case 'handlebars':
          case 'razor':
            return new htmlWorker();
          case 'typescript':
          case 'javascript':
            return new tsWorker();
          default:
            return new editorWorker();
        }
      },
    };

    loader.config({ monaco });
    return monaco;
  });

  return setupPromise;
}
