// PostHog product analytics: page views and time spent on each screen.
//
// Most of the app is one URL that swaps screens via React state (chat, topics,
// dashboard...), so automatic URL-based pageviews would miss them. Instead each
// screen change is reported by trackScreen(), which sends a $pageview for the
// new screen and a `screen_time` event with the seconds spent on the old one.
//
// Disabled (every call is a no-op) unless VITE_POSTHOG_KEY is set at build time.
import posthog from 'posthog-js';

const KEY = (import.meta.env.VITE_POSTHOG_KEY as string | undefined) ?? '';
const HOST = (import.meta.env.VITE_POSTHOG_HOST as string | undefined) || 'https://us.i.posthog.com';

let enabled = false;
let current: { screen: string; since: number } | null = null;

export function initAnalytics(): void {
  if (!KEY || enabled) return;
  posthog.init(KEY, {
    api_host: HOST,
    capture_pageview: false, // sent manually per screen, see trackScreen
    capture_pageleave: false,
    persistence: 'localStorage+cookie',
  });
  enabled = true;
  // Close the open screen when the tab is hidden or closed, and restart its
  // timer when the tab comes back, so idle background time is not counted.
  document.addEventListener('visibilitychange', () => {
    if (!current) return;
    if (document.visibilityState === 'hidden') {
      flush();
    } else {
      current.since = Date.now();
    }
  });
}

function flush(): void {
  if (!enabled || !current) return;
  const seconds = Math.round((Date.now() - current.since) / 1000);
  if (seconds > 0) {
    posthog.capture('screen_time', { screen: current.screen, seconds }, { transport: 'sendBeacon' });
  }
  current.since = Date.now();
}

export function trackScreen(screen: string): void {
  if (!enabled || current?.screen === screen) return;
  flush();
  current = { screen, since: Date.now() };
  posthog.capture('$pageview', {
    screen,
    $current_url: `${window.location.origin}/${screen}`,
    $pathname: `/${screen}`,
  });
}

export function identifyUser(userId: string, props: { email?: string; name?: string } = {}): void {
  if (!enabled || !userId) return;
  posthog.identify(userId, props);
}

export function resetAnalytics(): void {
  if (!enabled) return;
  flush();
  current = null;
  posthog.reset();
}
