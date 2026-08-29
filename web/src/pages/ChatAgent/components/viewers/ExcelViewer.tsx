import React, { useState, useEffect } from 'react';
import ExcelJS from 'exceljs';
import './ExcelViewer.css';

const MAX_PREVIEW_ROWS = 500;

// Default Office theme colors for when theme index is used without resolved ARGB
const DEFAULT_THEME_COLORS = [
  'FFFFFF', '000000', 'E7E6E6', '44546A',
  '4472C4', 'ED7D31', 'A5A5A5', 'FFC000', '5B9BD5', '70AD47',
];

interface ExcelColor {
  argb?: string;
  theme?: number;
  tint?: number;
}

interface CellData {
  value: string;
  style: React.CSSProperties;
}

interface SheetData {
  name: string;
  rows: CellData[][];
  totalRows: number;
}

function applyTint(hex: string, tint: number): string {
  if (!tint) return hex;
  let r = parseInt(hex.slice(0, 2), 16);
  let g = parseInt(hex.slice(2, 4), 16);
  let b = parseInt(hex.slice(4, 6), 16);
  if (tint > 0) {
    r = Math.round(r + (255 - r) * tint);
    g = Math.round(g + (255 - g) * tint);
    b = Math.round(b + (255 - b) * tint);
  } else {
    r = Math.round(r * (1 + tint));
    g = Math.round(g * (1 + tint));
    b = Math.round(b * (1 + tint));
  }
  const clamp = (v: number) => Math.max(0, Math.min(255, v));
  r = clamp(r); g = clamp(g); b = clamp(b);
  return r.toString(16).padStart(2, '0') + g.toString(16).padStart(2, '0') + b.toString(16).padStart(2, '0');
}

function resolveColor(color: ExcelColor | undefined | null): string | null {
  if (!color) return null;
  if (color.argb) {
    const argb = color.argb;
    // ARGB format: skip alpha channel
    return '#' + (argb.length === 8 ? argb.slice(2) : argb);
  }
  if (color.theme != null) {
    const base = DEFAULT_THEME_COLORS[color.theme] || '000000';
    return '#' + (color.tint ? applyTint(base, color.tint) : base);
  }
  return null;
}

function getCellStyle(cell: ExcelJS.Cell | undefined | null): React.CSSProperties {
  const style: React.CSSProperties = {};
  if (!cell) return style;

  // Background fill
  const fill = cell.fill as ExcelJS.FillPattern | undefined;
  if (fill?.type === 'pattern' && fill.pattern !== 'none' && fill.fgColor) {
    const bg = resolveColor(fill.fgColor as ExcelColor);
    if (bg) style.backgroundColor = bg;
  }

  // Font
  const font = cell.font;
  if (font) {
    if (font.bold) style.fontWeight = 'bold';
    if (font.italic) style.fontStyle = 'italic';
    const decorations: string[] = [];
    if (font.underline) decorations.push('underline');
    if (font.strike) decorations.push('line-through');
    if (decorations.length) style.textDecoration = decorations.join(' ');
    const fontColor = resolveColor(font.color as ExcelColor | undefined);
    if (fontColor) style.color = fontColor;
    if (font.size) style.fontSize = `${font.size}pt`;
  }

  // Alignment
  const align = cell.alignment;
  if (align) {
    if (align.horizontal) style.textAlign = align.horizontal as React.CSSProperties['textAlign'];
    if (align.vertical === 'middle') style.verticalAlign = 'middle';
    else if (align.vertical === 'top') style.verticalAlign = 'top';
    if (align.wrapText) style.whiteSpace = 'pre-wrap';
  }

  return style;
}

function getCellDisplayValue(cell: ExcelJS.Cell | undefined | null): string {
  if (!cell || cell.value == null) return '';
  const v = cell.value;
  if (typeof v === 'object') {
    // TODO: type properly — ExcelJS CellValue union is complex
    const obj = v as unknown as Record<string, unknown>;
    if (obj.richText) return (obj.richText as Array<{ text: string }>).map((r) => r.text).join('');
    if (obj.result != null) return String(obj.result);
    if (v instanceof Date) return v.toLocaleDateString();
    if (obj.hyperlink) return String(obj.text || obj.hyperlink);
    if (obj.error) return String(obj.error);
  }
  return String(v);
}

/** Parse workbook into plain data (runs async in effect) */
async function parseWorkbook(buffer: ArrayBuffer): Promise<SheetData[]> {
  const wb = new ExcelJS.Workbook();
  await wb.xlsx.load(buffer);

  return wb.worksheets.map((ws) => {
    const colCount = ws.columnCount;
    const rowCount = ws.rowCount;
    const previewCount = Math.min(rowCount, MAX_PREVIEW_ROWS);
    const rows: CellData[][] = [];

    for (let r = 1; r <= previewCount; r++) {
      const row = ws.getRow(r);
      const cells: CellData[] = [];
      for (let c = 1; c <= colCount; c++) {
        const cell = row.getCell(c);
        cells.push({
          value: getCellDisplayValue(cell),
          style: getCellStyle(cell),
        });
      }
      rows.push(cells);
    }

    return { name: ws.name, rows, totalRows: rowCount };
  });
}

interface ExcelViewerProps {
  data: ArrayBuffer;
}

export default function ExcelViewer({ data }: ExcelViewerProps) {
  const [sheets, setSheets] = useState<SheetData[] | null>(null);
  const [activeSheet, setActiveSheet] = useState(0);
  const [parseError, setParseError] = useState<Error | null>(null);

  useEffect(() => {
    let cancelled = false;
    parseWorkbook(data)
      .then((result) => { if (!cancelled) setSheets(result); })
      .catch((err: Error) => {
        console.error('[ExcelViewer] Failed to parse workbook:', err);
        if (!cancelled) setParseError(err);
      });
    return () => { cancelled = true; };
  }, [data]);

  // Bubble to error boundary
  if (parseError) throw parseError;

  if (!sheets) {
    return <div className="excel-viewer-empty">Parsing spreadsheet...</div>;
  }
  if (sheets.length === 0) {
    throw new Error('No sheets found in workbook');
  }

  const sheet = sheets[activeSheet] || sheets[0];
  const { rows, totalRows } = sheet;

  if (rows.length === 0) {
    return <div className="excel-viewer-empty">This sheet is empty</div>;
  }

  const headerRow = rows[0];
  const dataRows = rows.slice(1);
  const truncated = totalRows > MAX_PREVIEW_ROWS;

  return (
    <div className="excel-viewer">
      {/* Sheet tabs */}
      {sheets.length > 1 && (
        <div className="excel-sheet-tabs">
          {sheets.map((s, idx) => (
            <button
              key={s.name}
              className={`excel-sheet-tab ${idx === activeSheet ? 'active' : ''}`}
              onClick={() => setActiveSheet(idx)}
            >
              {s.name}
            </button>
          ))}
        </div>
      )}

      {/* Table */}
      <div className="excel-table-wrapper">
        <table className="excel-table">
          <thead>
            <tr>
              <th className="excel-row-num">#</th>
              {headerRow.map((cell, ci) => (
                <th key={ci} style={cell.style}>{cell.value}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {dataRows.map((row, ri) => (
              <tr key={ri}>
                <td className="excel-row-num">{ri + 1}</td>
                {row.map((cell, ci) => (
                  <td key={ci} style={cell.style}>{cell.value}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {truncated && (
        <div className="excel-truncated">
          Showing first {MAX_PREVIEW_ROWS} of {totalRows} rows
        </div>
      )}
    </div>
  );
}
