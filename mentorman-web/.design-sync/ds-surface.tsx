import React from 'react';

/**
 * Preview surface for MentorMan cards. Not part of the app — design-sync only.
 *
 * MentorMan is a dark design system: globals.css paints html/body with
 * var(--bg). The preview scaffold hardcodes `body{padding:24px;background:#fff}`
 * in an inline <style> that lands after the stylesheets, so it always wins and
 * every card would render dark components floating on white. Wiring this as
 * cfg.provider repaints the card interior instead, which is the supported way
 * to do it (lib/emit.mjs is contract code and must not be forked).
 *
 * The negative margin cancels the scaffold's own 24px padding so the surface
 * reaches the card edges, then re-applies it inside.
 */
export function MentorManSurface({ children }: { children?: React.ReactNode }) {
  return (
    <div
      style={{
        margin: -24,
        padding: 24,
        minHeight: '100%',
        background: 'var(--bg)',
        color: 'var(--fg)',
        fontFamily: 'var(--sans)',
      }}
    >
      {children}
    </div>
  );
}
