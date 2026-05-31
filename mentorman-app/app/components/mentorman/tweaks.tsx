'use client';

import React, { useState, useRef, useCallback, useEffect } from 'react';

type TweakValues = Record<string, string>;

export function useTweaks(defaults: TweakValues): [TweakValues, (key: string, val: string) => void] {
  const [values, setValues] = useState(defaults);
  const setTweak = useCallback((key: string, val: string) => {
    setValues(prev => ({ ...prev, [key]: val }));
  }, []);
  return [values, setTweak];
}

export function TweaksPanel({ title = 'Tweaks', children }: { title?: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          position: 'fixed', right: 18, bottom: 18, zIndex: 2147483645,
          height: 34, padding: '0 14px', borderRadius: 999,
          border: '1px solid var(--border)',
          background: 'color-mix(in oklch, var(--card) 80%, #000)',
          color: 'var(--muted-2)', fontFamily: 'var(--mono)', fontSize: 11,
          cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 7,
          backdropFilter: 'blur(10px)',
        }}
      >
        <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--accent)', boxShadow: '0 0 6px var(--accent-glow)' }} />
        tweaks
      </button>

      {open && (
        <div className="twk-panel" style={{ right: 18, bottom: 60 }}>
          <div className="twk-hd">
            <b>{title}</b>
            <button className="twk-x" onClick={() => setOpen(false)}>✕</button>
          </div>
          <div className="twk-body">{children}</div>
        </div>
      )}
    </>
  );
}

export function TweakSection({ label }: { label: string }) {
  return <div className="twk-sect">{label}</div>;
}

export function TweakRadio({ label, value, options, onChange }: {
  label: string;
  value: string;
  options: string[];
  onChange: (v: string) => void;
}) {
  const idx = options.indexOf(value);
  const n = options.length;
  return (
    <div className="twk-row">
      <div className="twk-lbl"><span>{label}</span></div>
      <div className="twk-seg">
        <div className="twk-seg-thumb" style={{
          left: `calc(2px + ${idx} * (100% - 4px) / ${n})`,
          width: `calc((100% - 4px) / ${n})`
        }} />
        {options.map(o => (
          <button key={o} type="button" onClick={() => onChange(o)}
                  style={{ fontWeight: o === value ? 600 : 500 }}>
            {o}
          </button>
        ))}
      </div>
    </div>
  );
}

export function TweakColor({ label, value, options, onChange }: {
  label: string;
  value: string;
  options: string[];
  onChange: (v: string) => void;
}) {
  return (
    <div className="twk-row">
      <div className="twk-lbl"><span>{label}</span></div>
      <div className="twk-chips">
        {options.map((o, i) => (
          <button key={i} type="button" className="twk-chip"
                  data-on={o === value ? '1' : '0'}
                  style={{ background: o }}
                  onClick={() => onChange(o)}>
            {o === value && (
              <svg viewBox="0 0 14 14" style={{ position: 'absolute', top: 6, left: 6, width: 13, height: 13 }}>
                <path d="M3 7.2 5.8 10 11 4.2" fill="none" strokeWidth="2.2"
                      strokeLinecap="round" strokeLinejoin="round" stroke="rgba(0,0,0,0.7)" />
              </svg>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}
