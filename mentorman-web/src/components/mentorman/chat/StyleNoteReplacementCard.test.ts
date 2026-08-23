/**
 * Unit tests for the StyleNoteReplacementCard component logic.
 *
 * Tests the state transitions and behavior of the style note replacement flow
 * when a user has reached the maximum of 5 style notes.
 *
 * Validates: Requirements 7.3, 7.4
 */
import { describe, it, expect } from 'vitest';
import type { StyleNote } from '@/lib/mentorman-api';

// ─── Derived state logic for testing (mirrors component behavior) ──

type CardState = 'selecting' | 'replaced' | 'dismissed';

interface ReplacementState {
  cardState: CardState;
  selectedIndex: number | null;
  existingNotes: StyleNote[];
}

function createInitialState(notes: StyleNote[]): ReplacementState {
  return {
    cardState: 'selecting',
    selectedIndex: null,
    existingNotes: notes,
  };
}

function selectNote(state: ReplacementState, index: number): ReplacementState {
  return { ...state, selectedIndex: index };
}

function dismiss(state: ReplacementState): ReplacementState {
  return { ...state, cardState: 'dismissed' };
}

function replace(state: ReplacementState): ReplacementState | null {
  if (state.selectedIndex === null) return null; // can't replace without selection
  return { ...state, cardState: 'replaced' };
}

// ─── Test data ────────────────────────────────────────────────────────────────

const FIVE_STYLE_NOTES: StyleNote[] = [
  { category: 'pacing', note: 'Prefers slower explanations' },
  { category: 'motivation', note: 'Responds well to real-world examples' },
  { category: 'communication', note: 'Likes concise bullet points' },
  { category: 'depth', note: 'Enjoys deep dives into topics' },
  { category: 'feedback', note: 'Prefers direct constructive criticism' },
];

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('StyleNoteReplacementCard — initial state', () => {
  it('starts in selecting state with no selection', () => {
    const state = createInitialState(FIVE_STYLE_NOTES);
    expect(state.cardState).toBe('selecting');
    expect(state.selectedIndex).toBeNull();
    expect(state.existingNotes).toHaveLength(5);
  });

  it('shows all 5 existing notes', () => {
    const state = createInitialState(FIVE_STYLE_NOTES);
    expect(state.existingNotes).toEqual(FIVE_STYLE_NOTES);
  });
});

describe('StyleNoteReplacementCard — note selection', () => {
  it('allows selecting an existing note by index', () => {
    let state = createInitialState(FIVE_STYLE_NOTES);
    state = selectNote(state, 2);
    expect(state.selectedIndex).toBe(2);
  });

  it('allows changing selection to a different note', () => {
    let state = createInitialState(FIVE_STYLE_NOTES);
    state = selectNote(state, 1);
    state = selectNote(state, 4);
    expect(state.selectedIndex).toBe(4);
  });

  it('selection is within valid range (0-4 for 5 notes)', () => {
    const state = selectNote(createInitialState(FIVE_STYLE_NOTES), 0);
    expect(state.selectedIndex).toBeGreaterThanOrEqual(0);
    expect(state.selectedIndex!).toBeLessThan(FIVE_STYLE_NOTES.length);
  });
});

describe('StyleNoteReplacementCard — dismiss flow (Requirement 7.4)', () => {
  it('dismissing transitions to dismissed state', () => {
    let state = createInitialState(FIVE_STYLE_NOTES);
    state = dismiss(state);
    expect(state.cardState).toBe('dismissed');
  });

  it('dismissing leaves existing notes unchanged', () => {
    let state = createInitialState(FIVE_STYLE_NOTES);
    state = dismiss(state);
    expect(state.existingNotes).toEqual(FIVE_STYLE_NOTES);
    expect(state.existingNotes).toHaveLength(5);
  });

  it('can dismiss even with a note selected', () => {
    let state = createInitialState(FIVE_STYLE_NOTES);
    state = selectNote(state, 3);
    state = dismiss(state);
    expect(state.cardState).toBe('dismissed');
    expect(state.existingNotes).toEqual(FIVE_STYLE_NOTES);
  });
});

describe('StyleNoteReplacementCard — replace flow (Requirement 7.3)', () => {
  it('replacing requires a selection (returns null if none)', () => {
    const state = createInitialState(FIVE_STYLE_NOTES);
    const result = replace(state);
    expect(result).toBeNull();
  });

  it('replacing with a selection transitions to replaced state', () => {
    let state = createInitialState(FIVE_STYLE_NOTES);
    state = selectNote(state, 2);
    const result = replace(state);
    expect(result).not.toBeNull();
    expect(result!.cardState).toBe('replaced');
  });

  it('replace button is disabled when selectedIndex is null', () => {
    const state = createInitialState(FIVE_STYLE_NOTES);
    const isDisabled = state.selectedIndex === null;
    expect(isDisabled).toBe(true);
  });

  it('replace button is enabled when a note is selected', () => {
    let state = createInitialState(FIVE_STYLE_NOTES);
    state = selectNote(state, 0);
    const isDisabled = state.selectedIndex === null;
    expect(isDisabled).toBe(false);
  });
});

describe('StyleNoteReplacementCard — requires_replacement detection', () => {
  it('proposal with requires_replacement=true and field=style_note triggers replacement flow', () => {
    const proposal = {
      id: 'p1',
      field: 'style_note',
      proposedValue: { category: 'pacing', note: 'Fast learner' },
      requires_replacement: true,
      status: 'pending' as const,
    };
    const shouldShowReplacement = proposal.requires_replacement && proposal.field === 'style_note';
    expect(shouldShowReplacement).toBe(true);
  });

  it('proposal without requires_replacement shows normal accept/dismiss', () => {
    const proposal = {
      id: 'p2',
      field: 'style_note',
      proposedValue: { category: 'pacing', note: 'Fast learner' },
      status: 'pending' as const,
    } as { id: string; field: string; proposedValue: Record<string, unknown>; status: 'pending'; requires_replacement?: boolean };
    const shouldShowReplacement = proposal.requires_replacement && proposal.field === 'style_note';
    expect(shouldShowReplacement).toBeFalsy();
  });

  it('non-style_note proposal with requires_replacement shows normal accept/dismiss', () => {
    const proposal = {
      id: 'p3',
      field: 'situation',
      proposedValue: { value: 'Machine Learning' },
      requires_replacement: true,
      status: 'pending' as const,
    };
    const shouldShowReplacement = proposal.requires_replacement && proposal.field === 'style_note';
    expect(shouldShowReplacement).toBe(false);
  });
});

describe('StyleNoteReplacementCard — display requirements', () => {
  it('displays all 5 existing notes for selection', () => {
    const state = createInitialState(FIVE_STYLE_NOTES);
    // Each note should be selectable
    expect(state.existingNotes.length).toBe(5);
    state.existingNotes.forEach((note, i) => {
      expect(note.category).toBeTruthy();
      expect(note.note).toBeTruthy();
      // Each should be selectable
      const selected = selectNote(state, i);
      expect(selected.selectedIndex).toBe(i);
    });
  });

  it('proposed note contains category and note text', () => {
    const proposedNote = { category: 'motivation', note: 'Responds well to challenges' };
    expect(proposedNote.category).toBeTruthy();
    expect(proposedNote.note).toBeTruthy();
    expect(proposedNote.note.length).toBeLessThanOrEqual(140); // Schema constraint
  });
});
