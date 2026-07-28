/**
 * Property-based tests for client-side document upload validation.
 *
 * Property 1: Client-side file validation partition
 * Property 2: Filename truncation and size formatting
 *
 * Validates: Requirements 1.3, 1.4, 1.5, 1.6, 1.7, 1.8
 */
import { describe, it, expect } from 'vitest';
import * as fc from 'fast-check';
import {
  validateDocumentFile,
  SUPPORTED_DOCUMENT_EXTENSIONS,
  MAX_DOCUMENT_SIZE_BYTES,
} from './document-upload-utils';
import { truncateFilename, formatFileSize } from './utils';

// --- Generators ---

const supportedExtensions: readonly string[] = SUPPORTED_DOCUMENT_EXTENSIONS;

const unsupportedExtensions = [
  '.exe', '.dll', '.bat', '.sh', '.py', '.js', '.ts',
  '.mp3', '.mp4', '.avi', '.zip', '.rar', '.7z', '.iso',
  '.bmp', '.gif', '.png', '.jpg', '.svg', '.html', '.xml',
];

/** Generate a safe base filename (alphanumeric, no dots/slashes). */
const safeBaseArb = fc.stringMatching(/^[a-zA-Z0-9_-]+$/, { minLength: 1, maxLength: 50 } as any);

/** Generate a filename with a supported extension. */
const supportedFilenameArb = fc.tuple(
  safeBaseArb,
  fc.constantFrom(...supportedExtensions),
).map(([base, ext]) => base + ext);

/** Generate a filename with an unsupported extension. */
const unsupportedFilenameArb = fc.tuple(
  safeBaseArb,
  fc.constantFrom(...unsupportedExtensions),
).map(([base, ext]) => base + ext);

/** Generate a filename with no extension (no dot). */
const noExtensionFilenameArb = safeBaseArb;

/** Generate a random filename (could be valid or invalid extension). */
const anyFilenameArb = fc.oneof(
  supportedFilenameArb,
  unsupportedFilenameArb,
  noExtensionFilenameArb,
);

/** Generate a valid file size (0 to MAX_DOCUMENT_SIZE_BYTES). */
const validSizeArb = fc.integer({ min: 0, max: MAX_DOCUMENT_SIZE_BYTES });

/** Generate an invalid file size (exceeds 10 MB). */
const invalidSizeArb = fc.integer({ min: MAX_DOCUMENT_SIZE_BYTES + 1, max: 20 * 1024 * 1024 });

/** Generate a random file size (0 to 20 MB). */
const anySizeArb = fc.integer({ min: 0, max: 20 * 1024 * 1024 });

/** Generate a random file metadata object (name + size). */
const anyFileArb = fc.tuple(anyFilenameArb, anySizeArb).map(([name, size]) => ({ name, size }));

// --- Property 1: Client-side file validation partition ---

describe('Property 1: Client-side file validation partition', () => {
  /**
   * **Validates: Requirements 1.3, 1.5, 1.6, 1.7, 1.8**
   *
   * For any set of files with random names, sizes, and extensions,
   * validateDocumentFile partitions them into valid (null) and invalid (error message)
   * sets such that the union equals the original and the intersection is empty.
   */
  it('every file is classified as exactly valid or invalid (union = original, intersection = empty)', () => {
    fc.assert(
      fc.property(
        fc.array(anyFileArb, { minLength: 0, maxLength: 10 }),
        (files) => {
          const validFiles: typeof files = [];
          const invalidFiles: typeof files = [];

          for (const file of files) {
            const result = validateDocumentFile(file);
            if (result === null) {
              validFiles.push(file);
            } else {
              invalidFiles.push(file);
            }
          }

          // Union equals original
          expect(validFiles.length + invalidFiles.length).toBe(files.length);

          // Intersection is empty — every file appears in exactly one set
          const validSet = new Set(validFiles);
          const invalidSet = new Set(invalidFiles);
          for (const file of files) {
            const inValid = validSet.has(file);
            const inInvalid = invalidSet.has(file);
            expect(inValid !== inInvalid).toBe(true);
          }
        },
      ),
      { numRuns: 100 },
    );
  });

  it('files with supported extension and size ≤ 10 MB are always valid', () => {
    fc.assert(
      fc.property(
        supportedFilenameArb,
        validSizeArb,
        (name, size) => {
          const result = validateDocumentFile({ name, size });
          expect(result).toBeNull();
        },
      ),
      { numRuns: 100 },
    );
  });

  it('files exceeding 10 MB are always invalid regardless of extension', () => {
    fc.assert(
      fc.property(
        supportedFilenameArb,
        invalidSizeArb,
        (name, size) => {
          const result = validateDocumentFile({ name, size });
          expect(result).not.toBeNull();
          expect(result).toContain('10 MB');
        },
      ),
      { numRuns: 100 },
    );
  });

  it('files with unsupported extension are always invalid regardless of size', () => {
    fc.assert(
      fc.property(
        unsupportedFilenameArb,
        validSizeArb,
        (name, size) => {
          const result = validateDocumentFile({ name, size });
          expect(result).not.toBeNull();
          expect(result).toContain('Unsupported');
        },
      ),
      { numRuns: 100 },
    );
  });

  it('files with no extension are always invalid', () => {
    fc.assert(
      fc.property(
        noExtensionFilenameArb,
        validSizeArb,
        (name, size) => {
          const result = validateDocumentFile({ name, size });
          expect(result).not.toBeNull();
        },
      ),
      { numRuns: 100 },
    );
  });
});

// --- Property 2: Filename truncation and size formatting ---

describe('Property 2: Filename truncation and size formatting', () => {
  /**
   * **Validates: Requirements 1.4**
   *
   * For any string (0–500 chars), truncateFilename returns a string of at most
   * 33 characters that starts with the same prefix as the original.
   */
  it('truncateFilename output is always ≤ 33 characters', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 0, maxLength: 500 }),
        (name) => {
          const truncated = truncateFilename(name);
          expect(truncated.length).toBeLessThanOrEqual(33);
        },
      ),
      { numRuns: 100 },
    );
  });

  it('truncateFilename preserves the original prefix', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 0, maxLength: 500 }),
        (name) => {
          const truncated = truncateFilename(name);
          if (name.length <= 30) {
            // If short enough, returned as-is
            expect(truncated).toBe(name);
          } else {
            // If truncated, first 30 chars match and ends with "..."
            expect(truncated.slice(0, 30)).toBe(name.slice(0, 30));
            expect(truncated.endsWith('...')).toBe(true);
          }
        },
      ),
      { numRuns: 100 },
    );
  });

  /**
   * **Validates: Requirements 1.4**
   *
   * For any file size (0–100 MB), formatFileSize returns:
   * - KB for sizes < 1 MB (1,048,576 bytes)
   * - MB with one decimal for sizes ≥ 1 MB
   * The numeric value is mathematically equivalent to the input.
   */
  it('formatFileSize uses KB for sizes < 1 MB and MB for sizes ≥ 1 MB', () => {
    const ONE_MB = 1_048_576;
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 100 * 1024 * 1024 }),
        (bytes) => {
          const formatted = formatFileSize(bytes);
          if (bytes < ONE_MB) {
            expect(formatted).toMatch(/^\d+ KB$/);
          } else {
            expect(formatted).toMatch(/^\d+\.\d MB$/);
          }
        },
      ),
      { numRuns: 100 },
    );
  });

  it('formatFileSize numeric value is mathematically equivalent to input', () => {
    const ONE_MB = 1_048_576;
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 100 * 1024 * 1024 }),
        (bytes) => {
          const formatted = formatFileSize(bytes);
          if (bytes < ONE_MB) {
            const kbValue = parseInt(formatted.replace(' KB', ''), 10);
            // Math.round(bytes / 1024) should equal the displayed value
            expect(kbValue).toBe(Math.round(bytes / 1024));
          } else {
            const mbValue = parseFloat(formatted.replace(' MB', ''));
            // (bytes / ONE_MB).toFixed(1) should equal the displayed value
            const expectedMb = parseFloat((bytes / ONE_MB).toFixed(1));
            expect(mbValue).toBeCloseTo(expectedMb, 1);
          }
        },
      ),
      { numRuns: 100 },
    );
  });
});
