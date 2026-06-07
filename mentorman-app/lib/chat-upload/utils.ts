/**
 * Chat file upload utility functions.
 *
 * Provides validation, formatting, and truncation helpers used by
 * the chat upload UI and session upload handler.
 */

const MAX_FILE_SIZE_BYTES = 10_485_760; // 10 MB
const ALLOWED_EXTENSIONS = [".pdf", ".csv"];
const MAX_FILENAME_LENGTH = 30;
const TRUNCATED_PREFIX_LENGTH = 27;
const DEFAULT_MESSAGE_LIMIT = 2000;
const ONE_MB = 1_048_576;

/**
 * Validates a file for upload eligibility.
 *
 * Checks that the file extension is `.pdf` or `.csv` and that the size
 * does not exceed 10 MB (10,485,760 bytes).
 *
 * @returns `null` if valid, or a user-facing error message string if invalid.
 */
export function validateUploadFile(file: {
  name: string;
  size: number;
}): string | null {
  const extension = file.name.includes(".")
    ? `.${file.name.split(".").pop()?.toLowerCase()}`
    : "";

  if (!ALLOWED_EXTENSIONS.includes(extension)) {
    return "Only .pdf and .csv files are supported";
  }

  if (file.size > MAX_FILE_SIZE_BYTES) {
    return "File must be under 10 MB";
  }

  return null;
}

/**
 * Truncates a filename for display.
 *
 * Returns the original string if its length is ≤ 30 characters,
 * or the first 27 characters followed by "..." if longer.
 * Output never exceeds 30 characters.
 */
export function truncateFilename(name: string): string {
  if (name.length <= MAX_FILENAME_LENGTH) {
    return name;
  }
  return name.slice(0, TRUNCATED_PREFIX_LENGTH) + "...";
}

/**
 * Formats a byte count as a human-readable file size string.
 *
 * - For sizes under 1 MB (1,048,576 bytes): displays as KB with no decimal.
 * - For sizes ≥ 1 MB: displays as MB with exactly one decimal place.
 */
export function formatFileSize(bytes: number): string {
  if (bytes < ONE_MB) {
    const kb = Math.round(bytes / 1024);
    return `${kb} KB`;
  }
  const mb = (bytes / ONE_MB).toFixed(1);
  return `${mb} MB`;
}

/**
 * Truncates a message string to the specified character limit.
 *
 * Returns the original string if its length is ≤ the limit (default 2000),
 * or the first `limit` characters if longer. Output never exceeds `limit` characters.
 */
export function truncateMessage(
  message: string,
  limit: number = DEFAULT_MESSAGE_LIMIT
): string {
  if (message.length <= limit) {
    return message;
  }
  return message.slice(0, limit);
}
