/**
 * Document upload utilities for the multi-file chat upload pipeline.
 *
 * Provides validation against the full set of Supported_Formats and
 * the 10 MB size limit. Extension-based validation is preferred over
 * MIME types because browser-reported MIME types can be unreliable.
 */

/** Maximum file size in bytes: 10 MB. */
export const MAX_DOCUMENT_SIZE_BYTES = 10_485_760;

/** Supported file extensions for the document upload pipeline. */
export const SUPPORTED_DOCUMENT_EXTENSIONS = [
  '.pdf',
  '.docx',
  '.csv',
  '.xlsx',
  '.json',
  '.txt',
  '.md',
  '.rtf',
] as const;

/** Human-readable list of supported formats for error messages. */
const SUPPORTED_FORMATS_DISPLAY = 'PDF, DOCX, CSV, XLSX, JSON, TXT, MD, RTF';

/**
 * Extracts the file extension from a filename (lowercased, including the dot).
 * Returns an empty string if no extension is found.
 */
function getFileExtension(filename: string): string {
  const lastDot = filename.lastIndexOf('.');
  if (lastDot === -1 || lastDot === filename.length - 1) return '';
  return filename.slice(lastDot).toLowerCase();
}

/**
 * Validates a file for the multi-file document upload pipeline.
 *
 * Checks:
 * 1. File extension is in SUPPORTED_DOCUMENT_EXTENSIONS
 * 2. File size does not exceed 10 MB (10,485,760 bytes)
 *
 * @returns `null` if valid, or a user-facing error message string if invalid.
 */
export function validateDocumentFile(file: { name: string; size: number }): string | null {
  const extension = getFileExtension(file.name);

  if (!extension || !(SUPPORTED_DOCUMENT_EXTENSIONS as readonly string[]).includes(extension)) {
    return `Unsupported format. Supported: ${SUPPORTED_FORMATS_DISPLAY}`;
  }

  if (file.size > MAX_DOCUMENT_SIZE_BYTES) {
    return 'File exceeds 10 MB maximum size';
  }

  return null;
}

export type FileValidationResult = {
  file: File;
  error: string | null;
};

/**
 * Validates an array of files and returns per-file validation results.
 */
export function validateDocumentFiles(files: File[]): FileValidationResult[] {
  return files.map((file) => ({
    file,
    error: validateDocumentFile(file),
  }));
}
