/**
 * Pin @monaco-editor/react to the locally bundled monaco instead of its
 * default jsdelivr CDN loader.
 *
 * Without this, the editor silently depends on https://cdn.jsdelivr.net being
 * reachable at runtime — which breaks every self-hosted / air-gapped /
 * firewalled deployment the moment a user opens a file, and makes the app
 * non-deterministic on the open internet too.
 *
 * Import this module ONCE, before the first <Editor> mounts (see main.tsx).
 * `monaco-editor` stays in devDependencies on purpose: Vite resolves the bare
 * import at build time and emits it into this chunk, so it is never fetched
 * from the network — only bundled.
 */
import { loader } from '@monaco-editor/react';
import * as monaco from 'monaco-editor';

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
