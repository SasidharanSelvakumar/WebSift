import {
  ExtractResponse,
  ExtractedItem,
  HealthStatus,
  MedicineBatch,
  SpreadsheetDestinationInfo,
  SpreadsheetPushResponse,
} from './types';

const API_BASE = '/api';

/**
 * Trigger browser file download from Blob and Filename
 */
function triggerBrowserDownload(blob: Blob, suggestedFilename: string) {
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.style.display = 'none';
  a.href = url;
  a.download = suggestedFilename;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => {
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
  }, 200);
}

/**
 * Extracts filename from Content-Disposition header
 */
function getFilenameFromHeader(headerValue: string | null, fallback: string): string {
  if (!headerValue) return fallback;
  const match = headerValue.match(/filename="?([^";]+)"?/i);
  return match && match[1] ? match[1] : fallback;
}

export async function checkBackendHealth(): Promise<HealthStatus> {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) {
    throw new Error(`Health check failed with status: ${res.status}`);
  }
  return res.json();
}

export async function extractWebpage(
  url: string,
  mode: 'main' | 'full' = 'main',
  forceBrowser: boolean = false
): Promise<ExtractResponse> {
  const res = await fetch(`${API_BASE}/extract`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      url,
      mode,
      force_browser: forceBrowser,
    }),
  });

  if (!res.ok) {
    let errorDetail = 'Extraction failed.';
    try {
      const errorJson = await res.json();
      errorDetail = errorJson.detail || errorDetail;
    } catch {
      errorDetail = `Server returned status ${res.status}`;
    }
    throw new Error(errorDetail);
  }

  return res.json();
}

export async function downloadCsv(
  items: ExtractedItem[],
  sourceUrl: string,
  pageTitle: string
): Promise<string> {
  const res = await fetch(`${API_BASE}/export/csv`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      items,
      source_url: sourceUrl,
      page_title: pageTitle,
    }),
  });

  if (!res.ok) {
    let errorDetail = 'CSV export failed.';
    try {
      const errorJson = await res.json();
      errorDetail = errorJson.detail || errorDetail;
    } catch {
      errorDetail = `Server returned ${res.status}`;
    }
    throw new Error(errorDetail);
  }

  const contentDisposition = res.headers.get('Content-Disposition');
  const filename = getFilenameFromHeader(contentDisposition, 'websift_export.csv');
  const blob = await res.blob();
  triggerBrowserDownload(blob, filename);
  return filename;
}

export async function downloadTxt(
  items: ExtractedItem[],
  sourceUrl: string,
  pageTitle: string,
  mode: string = 'main'
): Promise<string> {
  const res = await fetch(`${API_BASE}/export/txt`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      items,
      source_url: sourceUrl,
      page_title: pageTitle,
      mode,
    }),
  });

  if (!res.ok) {
    let errorDetail = 'TXT export failed.';
    try {
      const errorJson = await res.json();
      errorDetail = errorJson.detail || errorDetail;
    } catch {
      errorDetail = `Server returned ${res.status}`;
    }
    throw new Error(errorDetail);
  }

  const contentDisposition = res.headers.get('Content-Disposition');
  const filename = getFilenameFromHeader(contentDisposition, 'websift_export.txt');
  const blob = await res.blob();
  triggerBrowserDownload(blob, filename);
  return filename;
}

/**
 * Downloads a genuine Excel (.xlsx) file containing complete dynamic medicine records.
 */
export async function downloadExcel(
  batch: MedicineBatch,
  sourceUrl: string
): Promise<string> {
  const res = await fetch(`${API_BASE}/export/excel`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      batch,
      source_url: sourceUrl,
    }),
  });

  if (!res.ok) {
    let errorDetail = 'Excel export failed.';
    try {
      const errorJson = await res.json();
      errorDetail = errorJson.detail || errorDetail;
    } catch {
      errorDetail = `Server returned ${res.status}`;
    }
    throw new Error(errorDetail);
  }

  const contentDisposition = res.headers.get('Content-Disposition');
  const filename = getFilenameFromHeader(contentDisposition, 'medicine_data.xlsx');
  const blob = await res.blob();
  triggerBrowserDownload(blob, filename);
  return filename;
}

/**
 * Downloads dynamic medicine CSV with all discovered attribute columns.
 */
export async function downloadMedicineCsv(
  batch: MedicineBatch,
  sourceUrl: string
): Promise<string> {
  const res = await fetch(`${API_BASE}/export/medicine-csv`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      batch,
      source_url: sourceUrl,
    }),
  });

  if (!res.ok) {
    let errorDetail = 'Medicine CSV export failed.';
    try {
      const errorJson = await res.json();
      errorDetail = errorJson.detail || errorDetail;
    } catch {
      errorDetail = `Server returned ${res.status}`;
    }
    throw new Error(errorDetail);
  }

  const contentDisposition = res.headers.get('Content-Disposition');
  const filename = getFilenameFromHeader(contentDisposition, 'medicine_data.csv');
  const blob = await res.blob();
  triggerBrowserDownload(blob, filename);
  return filename;
}

/**
 * Downloads human-readable medicine TXT cards.
 */
export async function downloadMedicineTxt(
  batch: MedicineBatch,
  sourceUrl: string
): Promise<string> {
  const res = await fetch(`${API_BASE}/export/medicine-txt`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      batch,
      source_url: sourceUrl,
    }),
  });

  if (!res.ok) {
    let errorDetail = 'Medicine TXT export failed.';
    try {
      const errorJson = await res.json();
      errorDetail = errorJson.detail || errorDetail;
    } catch {
      errorDetail = `Server returned ${res.status}`;
    }
    throw new Error(errorDetail);
  }

  const contentDisposition = res.headers.get('Content-Disposition');
  const filename = getFilenameFromHeader(contentDisposition, 'medicine_data.txt');
  const blob = await res.blob();
  triggerBrowserDownload(blob, filename);
  return filename;
}

/**
 * Gets configured spreadsheet destinations.
 */
export async function getSpreadsheetDestinations(): Promise<SpreadsheetDestinationInfo[]> {
  const res = await fetch(`${API_BASE}/spreadsheet/destinations`);
  if (!res.ok) {
    throw new Error('Failed to fetch spreadsheet destinations');
  }
  return res.json();
}

/**
 * Pushes records into an existing local or cloud spreadsheet.
 */
export async function pushToSpreadsheet(
  batch: MedicineBatch,
  destinationType: 'local_excel' | 'google_sheets' = 'local_excel',
  targetFilePath?: string,
  spreadsheetId?: string,
  worksheetName: string = 'Medicine Data',
  preventDuplicates: boolean = true
): Promise<SpreadsheetPushResponse> {
  const res = await fetch(`${API_BASE}/spreadsheet/push`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      batch,
      destination_type: destinationType,
      target_file_path: targetFilePath,
      spreadsheet_id: spreadsheetId,
      worksheet_name: worksheetName,
      prevent_duplicates: preventDuplicates,
    }),
  });

  if (!res.ok) {
    let errorDetail = 'Spreadsheet push failed.';
    try {
      const errorJson = await res.json();
      errorDetail = errorJson.detail || errorDetail;
    } catch {
      errorDetail = `Server returned ${res.status}`;
    }
    throw new Error(errorDetail);
  }

  return res.json();
}
