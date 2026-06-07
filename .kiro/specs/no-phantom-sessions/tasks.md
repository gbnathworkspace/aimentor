# Implementation Plan — No Phantom Sessions & Upload Status

## Tasks

- [x] 1. Stop phantom session creation
  - [x] 1.1 Remove session creation from the auto-greet (greeting only)
    - _Requirements: 1.1_
  - [x] 1.2 Add `ensureSession()` — lazy, single, in-flight-guarded; refresh sidebar on create
    - _Requirements: 1.2, 1.3, 2.1_
  - [x] 1.3 `send()` creates the session on first message via `ensureSession`
    - _Requirements: 1.2_

- [x] 2. Resume the same session across reloads
  - [x] 2.1 Persist `backendSessionId` in the draft; restore it on load
    - _Requirements: 1.4_

- [x] 3. Upload-first still works
  - [x] 3.1 `handleFileSelected` triggers `ensureSession`; effect submits the pending file once the session exists
    - _Requirements: 4.2_

- [x] 4. Fix upload-status timeout
  - [x] 4.1 Backend reports terminal `done` (+ extractionReady) on success, `failed` otherwise
    - _Requirements: 3.1, 3.2, 3.3_

- [x] 5. Verify
  - [x] SPA builds clean; backend suite green (163); backend restarted; fresh build served
    - _Requirements: 4.1_
