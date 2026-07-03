'use client';

import React from 'react';

type IconName =
  | 'plus' | 'chart' | 'gear' | 'send' | 'arrowUp' | 'check'
  | 'upload' | 'code' | 'spark' | 'warn' | 'x' | 'arrowR'
  | 'back' | 'target' | 'clock' | 'bolt' | 'doc' | 'dots' | 'logout'
  | 'volume' | 'stop';

const I: Record<IconName, React.ReactNode> = {
  plus:    <path d="M8 3v10M3 8h10" />,
  chart:   <g><path d="M2 13.5V2.5M2 13.5H14" /><rect x="4" y="8" width="2.2" height="3.5" /><rect x="7.4" y="5" width="2.2" height="6.5" /><rect x="10.8" y="9.2" width="2.2" height="2.3" /></g>,
  gear:    <g><circle cx="8" cy="8" r="2.4" /><path d="M8 1.5v1.8M8 12.7v1.8M14.5 8h-1.8M3.3 8H1.5M12.6 3.4l-1.3 1.3M4.7 11.3l-1.3 1.3M12.6 12.6l-1.3-1.3M4.7 4.7L3.4 3.4" /></g>,
  send:    <path d="M3 8h9M8 4l4 4-4 4" />,
  arrowUp: <path d="M8 13V3M4 7l4-4 4 4" />,
  check:   <path d="M3 8.5l3.2 3.2L13 4.5" />,
  upload:  <g><path d="M8 10.5V3M5 6l3-3 3 3" /><path d="M3 11.5v1.5h10v-1.5" /></g>,
  code:    <path d="M5.5 5.5L2.5 8l3 2.5M10.5 5.5L13.5 8l-3 2.5M9 4l-2 8" />,
  spark:   <path d="M8 2l1.3 3.7L13 7l-3.7 1.3L8 12l-1.3-3.7L3 7l3.7-1.3z" />,
  warn:    <g><path d="M8 2.5L14.5 13.5H1.5z" /><path d="M8 6.5v3.2M8 11.6v.2" /></g>,
  x:       <path d="M4 4l8 8M12 4l-8 8" />,
  arrowR:  <path d="M3 8h9M8.5 4.5L12 8l-3.5 3.5" />,
  back:    <path d="M10 3.5L5.5 8l4.5 4.5" />,
  target:  <g><circle cx="8" cy="8" r="5.5" /><circle cx="8" cy="8" r="2.3" /></g>,
  clock:   <g><circle cx="8" cy="8" r="5.5" /><path d="M8 5v3l2 1.4" /></g>,
  bolt:    <path d="M9 2L3.5 9H8l-1 5L12.5 7H8z" />,
  doc:     <g><path d="M4 2.5h5l3 3v8H4z" /><path d="M9 2.5v3h3" /></g>,
  dots:    <g><circle cx="3.5" cy="8" r="1" /><circle cx="8" cy="8" r="1" /><circle cx="12.5" cy="8" r="1" /></g>,
  logout:  <g><path d="M6 3H3.5a1 1 0 00-1 1v8a1 1 0 001 1H6M10 11l3-3-3-3M13 8H6" /></g>,
  volume:  <g><path d="M2 6h2.5L8 3.2v9.6L4.5 10H2z" /><path d="M10.8 5.5a3.5 3.5 0 010 5" /><path d="M12.6 3.7a6 6 0 010 8.6" /></g>,
  stop:    <rect x="3.5" y="3.5" width="9" height="9" rx="1.5" />,
};

export function Icon({ name, size = 16, style }: { name: IconName; size?: number; style?: React.CSSProperties }) {
  return (
    <svg viewBox="0 0 16 16" width={size} height={size} fill="none"
         stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={style}>
      {I[name]}
    </svg>
  );
}
