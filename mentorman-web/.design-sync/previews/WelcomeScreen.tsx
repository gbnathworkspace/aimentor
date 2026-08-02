import React from 'react';
import { WelcomeScreen } from 'mentorman-web';

// The chat panel's empty state. Renders statically — it holds its own composer
// text in local state and only calls onStart/onNav on interaction.

const noop = () => {};

/** The screen as a returning learner sees it. */
export function Default() {
  return (
    <div style={{ height: 620, display: 'flex' }}>
      <WelcomeScreen userName="Gopinath" mode="topic" onStart={noop} onNav={noop} />
    </div>
  );
}

/** No name resolved yet — the greeting degrades to a plain "Welcome". */
export function NoName() {
  return (
    <div style={{ height: 620, display: 'flex' }}>
      <WelcomeScreen mode="topic" onStart={noop} onNav={noop} />
    </div>
  );
}

/** Mid-creation: composer and starter prompts lock while the topic is opened. */
export function Starting() {
  return (
    <div style={{ height: 620, display: 'flex' }}>
      <WelcomeScreen userName="Gopinath" mode="topic" busy onStart={noop} onNav={noop} />
    </div>
  );
}

/** Topic creation failed — the error sits under the starter prompts. */
export function WithError() {
  return (
    <div style={{ height: 620, display: 'flex' }}>
      <WelcomeScreen
        userName="Gopinath"
        mode="topic"
        error="Connection error — please try again."
        onStart={noop}
        onNav={noop}
      />
    </div>
  );
}
