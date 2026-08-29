import React from 'react';
import Editor, { DiffEditor } from '@monaco-editor/react';
import type { editor } from 'monaco-editor';

const EXT_TO_MONACO_LANG: Record<string, string> = {
  py: 'python', js: 'javascript', jsx: 'javascript', ts: 'typescript', tsx: 'typescript',
  json: 'json', md: 'markdown', yaml: 'yaml', yml: 'yaml', sql: 'sql',
  sh: 'shell', bash: 'shell', rs: 'rust', rb: 'ruby', go: 'go', java: 'java',
  xml: 'xml', css: 'css', html: 'html', htm: 'html', toml: 'ini', cfg: 'ini', ini: 'ini',
  txt: 'plaintext', csv: 'plaintext', env: 'shell', log: 'plaintext',
};

function getLanguageFromFileName(fileName: string | undefined): string {
  const ext = (fileName || '').split('.').pop()?.toLowerCase() || '';
  return EXT_TO_MONACO_LANG[ext] || 'plaintext';
}

function getTheme(): string {
  if (typeof document !== 'undefined' && document.documentElement.getAttribute('data-theme') === 'light') {
    return 'vs';
  }
  return 'vs-dark';
}

const EDITOR_OPTIONS: editor.IStandaloneEditorConstructionOptions = {
  minimap: { enabled: false },
  lineNumbers: 'on',
  wordWrap: 'on',
  scrollBeyondLastLine: false,
  fontSize: 12,
  automaticLayout: true,
  padding: { top: 8 },
};

interface TextSelection {
  text: string;
  startLine: number;
  endLine: number;
  rect: { left: number; top: number; width: number; height: number } | null;
}

interface UndoRedoState {
  canUndo: boolean;
  canRedo: boolean;
}

interface CodeEditorProps {
  value: string | undefined;
  onChange?: (value: string) => void;
  fileName?: string;
  readOnly?: boolean;
  height?: string;
  diffMode?: boolean;
  originalValue?: string;
  editorRef?: React.MutableRefObject<editor.IStandaloneCodeEditor | null>;
  onUndoRedoChange?: (state: UndoRedoState) => void;
  onTextSelect?: (selection: TextSelection | null) => void;
}

export default function CodeEditor({ value, onChange, fileName, readOnly = false, height = '100%', diffMode = false, originalValue, editorRef, onUndoRedoChange, onTextSelect }: CodeEditorProps) {
  const language = getLanguageFromFileName(fileName);
  const theme = getTheme();
  const showDiff = diffMode && originalValue != null;

  // Track DiffEditor listener disposables to prevent "TextModel got disposed" race
  const diffDisposablesRef = React.useRef<{ dispose(): void }[]>([]);
  const diffDisposedRef = React.useRef(false);

  React.useEffect(() => {
    if (showDiff) {
      diffDisposedRef.current = false;
    }
    return () => {
      diffDisposedRef.current = true;
      diffDisposablesRef.current.forEach((d) => d.dispose());
      diffDisposablesRef.current = [];
    };
  }, [showDiff]);

  return (
    <div style={{ position: 'relative', height, width: '100%' }}>
      {/* Always-mounted editor — preserves undo stack across diff toggles */}
      <div style={showDiff ? { position: 'absolute', inset: 0, visibility: 'hidden', pointerEvents: 'none' } : { height: '100%' }}>
        <Editor
          height="100%"
          language={language}
          theme={theme}
          value={value ?? ''}
          onMount={(monacoEditor: editor.IStandaloneCodeEditor) => {
            if (editorRef) editorRef.current = monacoEditor;
            let undoDepth = 0;
            let redoDepth = 0;
            onUndoRedoChange?.({ canUndo: false, canRedo: false });
            monacoEditor.onDidChangeModelContent((e) => {
              if (e.isUndoing) {
                undoDepth--;
                redoDepth++;
              } else if (e.isRedoing) {
                undoDepth++;
                redoDepth--;
              } else {
                undoDepth++;
                redoDepth = 0;
              }
              onUndoRedoChange?.({ canUndo: undoDepth > 0, canRedo: redoDepth > 0 });
              onChange?.(monacoEditor.getValue());
            });
            // Text selection callback for "Add to context"
            if (onTextSelect) {
              monacoEditor.onDidChangeCursorSelection(() => {
                const sel = monacoEditor.getSelection();
                if (!sel || sel.isEmpty()) {
                  onTextSelect(null);
                  return;
                }
                const text = monacoEditor.getModel()?.getValueInRange(sel);
                if (!text?.trim()) {
                  onTextSelect(null);
                  return;
                }
                // Get visual position of selection start for tooltip placement
                const pos = monacoEditor.getScrolledVisiblePosition(sel.getStartPosition());
                const editorDom = monacoEditor.getDomNode();
                const editorRect = editorDom?.getBoundingClientRect();
                const rect = (pos && editorRect) ? {
                  left: editorRect.left + pos.left,
                  top: editorRect.top + pos.top,
                  width: 0,
                  height: pos.height || 18,
                } : null;
                onTextSelect({ text, startLine: sel.startLineNumber, endLine: sel.endLineNumber, rect });
              });
            }
          }}
          options={{ ...EDITOR_OPTIONS, readOnly }}
        />
      </div>
      {/* Diff overlay — edits here flow back to the normal editor via onChange → value prop */}
      {showDiff && (
        <div style={{ position: 'absolute', inset: 0 }}>
          <DiffEditor
            height="100%"
            language={language}
            theme={theme}
            original={originalValue}
            modified={value ?? ''}
            onMount={(diffEditor: editor.IStandaloneDiffEditor) => {
              // Dispose any stale listeners from a previous mount
              diffDisposablesRef.current.forEach((d) => d.dispose());
              diffDisposablesRef.current = [];

              const modifiedEditor = diffEditor.getModifiedEditor();
              diffDisposablesRef.current.push(
                modifiedEditor.onDidChangeModelContent(() => {
                  if (diffDisposedRef.current) return;
                  onChange?.(modifiedEditor.getValue());
                }),
              );
              if (onTextSelect) {
                diffDisposablesRef.current.push(
                  modifiedEditor.onDidChangeCursorSelection(() => {
                    if (diffDisposedRef.current) return;
                    const sel = modifiedEditor.getSelection();
                    if (!sel || sel.isEmpty()) {
                      onTextSelect(null);
                      return;
                    }
                    const text = modifiedEditor.getModel()?.getValueInRange(sel);
                    if (!text?.trim()) {
                      onTextSelect(null);
                      return;
                    }
                    const pos = modifiedEditor.getScrolledVisiblePosition(sel.getStartPosition());
                    const editorDom = modifiedEditor.getDomNode();
                    const editorRect = editorDom?.getBoundingClientRect();
                    const rect = (pos && editorRect) ? {
                      left: editorRect.left + pos.left,
                      top: editorRect.top + pos.top,
                      width: 0,
                      height: pos.height || 18,
                    } : null;
                    onTextSelect({ text, startLine: sel.startLineNumber, endLine: sel.endLineNumber, rect });
                  }),
                );
              }
            }}
            options={{ ...EDITOR_OPTIONS, readOnly, renderSideBySide: true }}
          />
        </div>
      )}
    </div>
  );
}
