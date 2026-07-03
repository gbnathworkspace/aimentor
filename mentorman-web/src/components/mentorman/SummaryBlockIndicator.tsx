'use client';

import React, { useState } from 'react';

export interface SummaryBlockIndicatorProps {
  summaryBlock: {
    type: 'summary';
    id: string;
    summary: string;
    compactedRange: { from: string | Date; to: string | Date };
    messageCount: number;
    tokenCount: number;
  };
}

/**
 * Checks if two dates fall on the same calendar day.
 */
function isSameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

/**
 * Formats a compacted date range.
 * Same day: "Jan 5, 2024"
 * Different days: "Jan 5 – Jan 8, 2024"
 */
function formatDateRange(from: Date | string, to: Date | string): string {
  const fromDate = new Date(from);
  const toDate = new Date(to);
  const fmt = new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });

  if (isSameDay(fromDate, toDate)) {
    return fmt.format(fromDate);
  }

  const fmtNoYear = new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
  });
  return `${fmtNoYear.format(fromDate)} – ${fmt.format(toDate)}`;
}

/**
 * SummaryBlockIndicator renders a compacted summary block inline within the
 * chat conversation flow. It shows a collapsed pill-like indicator by default,
 * and expands to reveal the full narrative summary on click.
 *
 * Requirements: 11.1, 11.2, 11.3, 11.4, 11.5
 */
export function SummaryBlockIndicator({ summaryBlock }: SummaryBlockIndicatorProps) {
  const [expanded, setExpanded] = useState(false);

  const { summary, compactedRange, messageCount } = summaryBlock;
  const dateLabel = formatDateRange(compactedRange.from, compactedRange.to);

  return (
    <div className="summary-block" data-testid="summary-block">
      <button
        className="summary-block__header"
        onClick={() => setExpanded((prev) => !prev)}
        aria-expanded={expanded}
        aria-label={
          expanded
            ? 'Collapse summary of earlier messages'
            : `Expand summary of ${messageCount} earlier messages`
        }
        type="button"
      >
        <span className="summary-block__icon" aria-hidden="true">
          🗂️
        </span>
        <span className="summary-block__label">
          {messageCount} earlier message{messageCount !== 1 ? 's' : ''} summarized
        </span>
        <span className="summary-block__separator" aria-hidden="true">
          ·
        </span>
        <span className="summary-block__date">{dateLabel}</span>
        <span
          className={`summary-block__chevron ${expanded ? 'summary-block__chevron--open' : ''}`}
          aria-hidden="true"
        >
          ▾
        </span>
      </button>

      {expanded && (
        <div className="summary-block__content" data-testid="summary-block-content">
          {summary}
        </div>
      )}
    </div>
  );
}
