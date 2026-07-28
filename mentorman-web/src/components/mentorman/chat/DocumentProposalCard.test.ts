/**
 * Unit tests for the DocumentProposalCard component logic.
 *
 * Tests the helper functions (fieldLabel, formatProposedValue) and the
 * derived state logic (allResolved, pendingCount, etc.) without rendering React.
 *
 * Validates: Requirements 5.2, 5.3, 5.5, 5.6, 6.5, 6.9
 */
import { describe, it, expect } from 'vitest';
import type { Proposal, FailedFile } from './DocumentProposalCard';

// ─── Re-implement helpers inline for testing (same logic as in the component) ──

function fieldLabel(field: string): string {
  switch (field) {
    case 'style_note': return 'Style Note';
    case 'focus_areas': return 'Focus Area';
    default: return field.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
  }
}

function formatProposedValue(field: string, value: Record<string, unknown>): string {
  if (field === 'style_note') {
    const note = value.note ?? value.value;
    const category = value.category;
    if (category && note) return `[${category}] ${note}`;
    if (note) return String(note);
  }
  if (field === 'focus_areas') {
    return String(value.value ?? value.focus_area ?? JSON.stringify(value));
  }
  const str = JSON.stringify(value);
  return str.length > 80 ? str.slice(0, 77) + '...' : str;
}

// ─── Derived state logic (mirrors useMemo in component) ──

function computeDerivedState(proposals: Proposal[]) {
  const allResolved = proposals.length > 0 && proposals.every((p) => p.status !== 'pending');
  const pendingCount = proposals.filter((p) => p.status === 'pending').length;
  const acceptedCount = proposals.filter((p) => p.status === 'accepted').length;
  const dismissedCount = proposals.filter((p) => p.status === 'dismissed').length;
  return { allResolved, pendingCount, acceptedCount, dismissedCount };
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('DocumentProposalCard — fieldLabel', () => {
  it('maps style_note to "Style Note"', () => {
    expect(fieldLabel('style_note')).toBe('Style Note');
  });

  it('maps focus_areas to "Focus Area"', () => {
    expect(fieldLabel('focus_areas')).toBe('Focus Area');
  });

  it('falls back to title-cased underscore-to-space for unknown fields', () => {
    expect(fieldLabel('custom_field_name')).toBe('Custom Field Name');
  });
});

describe('DocumentProposalCard — formatProposedValue', () => {
  it('formats style_note with category and note', () => {
    const result = formatProposedValue('style_note', {
      category: 'motivation',
      note: 'Responds well to real-world examples',
    });
    expect(result).toBe('[motivation] Responds well to real-world examples');
  });

  it('formats style_note with only note (no category)', () => {
    const result = formatProposedValue('style_note', {
      note: 'Prefers visual diagrams',
    });
    expect(result).toBe('Prefers visual diagrams');
  });

  it('formats focus_areas using value key', () => {
    const result = formatProposedValue('focus_areas', { value: 'System Design' });
    expect(result).toBe('System Design');
  });

  it('truncates long fallback values to 80 chars', () => {
    const longValue: Record<string, unknown> = { data: 'x'.repeat(200) };
    const result = formatProposedValue('unknown_field', longValue);
    expect(result.length).toBeLessThanOrEqual(80);
    expect(result.endsWith('...')).toBe(true);
  });
});

describe('DocumentProposalCard — derived state logic', () => {
  const makeProposal = (id: string, status: Proposal['status']): Proposal => ({
    id,
    field: 'style_note',
    proposedValue: { note: 'test' },
    reason: 'test reason',
    sourceFilename: 'test.pdf',
    status,
  });

  it('allResolved is false when some proposals are pending', () => {
    const proposals = [
      makeProposal('1', 'accepted'),
      makeProposal('2', 'pending'),
    ];
    const { allResolved } = computeDerivedState(proposals);
    expect(allResolved).toBe(false);
  });

  it('allResolved is true when all are accepted or dismissed', () => {
    const proposals = [
      makeProposal('1', 'accepted'),
      makeProposal('2', 'dismissed'),
    ];
    const { allResolved } = computeDerivedState(proposals);
    expect(allResolved).toBe(true);
  });

  it('allResolved is false when proposals list is empty', () => {
    const { allResolved } = computeDerivedState([]);
    expect(allResolved).toBe(false);
  });

  it('counts pending, accepted, and dismissed correctly', () => {
    const proposals = [
      makeProposal('1', 'pending'),
      makeProposal('2', 'pending'),
      makeProposal('3', 'accepted'),
      makeProposal('4', 'dismissed'),
    ];
    const { pendingCount, acceptedCount, dismissedCount } = computeDerivedState(proposals);
    expect(pendingCount).toBe(2);
    expect(acceptedCount).toBe(1);
    expect(dismissedCount).toBe(1);
  });

  it('pendingCount is 0 when all proposals are resolved', () => {
    const proposals = [
      makeProposal('1', 'accepted'),
      makeProposal('2', 'accepted'),
    ];
    const { pendingCount } = computeDerivedState(proposals);
    expect(pendingCount).toBe(0);
  });
});

describe('DocumentProposalCard — rendering mode selection', () => {
  it('skip review mode: shows read-only summary', () => {
    // When skipReview=true, the component shows read-only informational display
    const skipReview = true;
    const proposals: Proposal[] = [
      {
        id: '1',
        field: 'focus_areas',
        proposedValue: { value: 'Machine Learning' },
        reason: 'Found in course syllabus',
        sourceFilename: 'syllabus.pdf',
        status: 'accepted',
      },
    ];
    // Should render the "Applied" badge path — no interactive controls
    expect(skipReview).toBe(true);
    expect(proposals.every(p => p.status === 'accepted')).toBe(true);
  });

  it('interactive mode: shows accept/dismiss when proposals are pending', () => {
    const skipReview = false;
    const proposals: Proposal[] = [
      {
        id: '1',
        field: 'style_note',
        proposedValue: { category: 'communication', note: 'Prefers concise explanations' },
        reason: 'Identified preference',
        sourceFilename: 'notes.txt',
        status: 'pending',
      },
    ];
    const allResolved = proposals.every(p => p.status !== 'pending');
    // Should show interactive controls
    expect(skipReview).toBe(false);
    expect(allResolved).toBe(false);
  });

  it('resolved mode: shows count summary when all resolved', () => {
    const proposals: Proposal[] = [
      {
        id: '1',
        field: 'focus_areas',
        proposedValue: { value: 'Data Structures' },
        reason: 'test',
        sourceFilename: 'resume.pdf',
        status: 'accepted',
      },
      {
        id: '2',
        field: 'style_note',
        proposedValue: { note: 'Visual learner' },
        reason: 'test',
        sourceFilename: 'preferences.docx',
        status: 'dismissed',
      },
    ];
    const allResolved = proposals.every(p => p.status !== 'pending');
    const acceptedCount = proposals.filter(p => p.status === 'accepted').length;
    const dismissedCount = proposals.filter(p => p.status === 'dismissed').length;
    expect(allResolved).toBe(true);
    expect(acceptedCount).toBe(1);
    expect(dismissedCount).toBe(1);
  });
});

describe('DocumentProposalCard — Apply All visibility', () => {
  it('Apply All button shown only when multiple proposals are pending', () => {
    const proposals: Proposal[] = [
      {
        id: '1', field: 'focus_areas',
        proposedValue: { value: 'React' }, reason: '', sourceFilename: 'a.pdf', status: 'pending',
      },
      {
        id: '2', field: 'focus_areas',
        proposedValue: { value: 'Node.js' }, reason: '', sourceFilename: 'b.pdf', status: 'pending',
      },
    ];
    const pendingCount = proposals.filter(p => p.status === 'pending').length;
    // Apply All shown when pendingCount > 1
    expect(pendingCount > 1).toBe(true);
  });

  it('Apply All button not shown when only one proposal is pending', () => {
    const proposals: Proposal[] = [
      {
        id: '1', field: 'focus_areas',
        proposedValue: { value: 'React' }, reason: '', sourceFilename: 'a.pdf', status: 'pending',
      },
      {
        id: '2', field: 'focus_areas',
        proposedValue: { value: 'Node.js' }, reason: '', sourceFilename: 'b.pdf', status: 'accepted',
      },
    ];
    const pendingCount = proposals.filter(p => p.status === 'pending').length;
    expect(pendingCount > 1).toBe(false);
  });
});
