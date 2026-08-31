# DepthWizard Frontend Coding Agent Contract

## Scope
- `frontend/` is the ONLY implementation area.
- `backend/` and `ml/` directories are strictly read-only for frontend agents.
- `backend/` and `ml/` may be inspected to understand API contracts, schemas, and pipeline outputs.
- NEVER modify code in `backend/` or `ml/` to resolve a frontend issue.
- NEVER invent or alter backend behavior in frontend code.
- Actual repository code and verified contracts take precedence over older prompts or historical notes.

## Stack
- **UI Library**: React 18
- **Build System**: Vite
- **Language**: TypeScript
- **Styling**: Tailwind CSS v4 (`@tailwindcss/vite`)
- **Routing**: React Router DOM v7
- **Authentication**: Supabase Auth (`@supabase/supabase-js`)
- **3D Engine**: Three.js (`three`)
- **Testing**: Playwright (`@playwright/test`)

## Architecture
- `src/app/`: Application root, routing, global provider/layout composition.
- `src/pages/`: Route-level screens (Auth, Input/Upload, Processing, Results).
- `src/components/`: Reusable presentation/UI components (`auth/`, `upload/`, `jobs/`, `results/`, `compare/`, `viewer/`).
- `src/hooks/`: Reusable stateful behavior (`useAuth`, `useJobPolling`, `useSignedAssets`).
- `src/lib/`: Core API client (`api.ts`), Supabase client (`supabase.ts`), TypeScript types (`types.ts`), error definitions (`errors.ts`), and utilities.
- `src/viewer/`: Three.js scene, rendering pipeline, WebGL lifecycle management.

**Separation Rules**:
- Keep API and network logic completely separate from UI component presentation.
- Keep Three.js WebGL scene management and vertex math isolated from page composition.

## Backend Contract

### Verified Endpoints
- `POST /api/v1/jobs`
- `GET /api/v1/jobs/{job_id}`
- `GET /api/v1/jobs/{job_id}/result`
- `GET /api/v1/jobs`
- `DELETE /api/v1/jobs/{job_id}`

### Job Creation
- Endpoint: `POST /api/v1/jobs`
- Request format: `multipart/form-data` with field name `file`
- HTTP Status: `202 Accepted`
- Response shape: `{ "job_id": "uuid", "status": "queued" }`

### Authentication
- Header: `Authorization: Bearer <Supabase access token>`
- Identity is verified via JWT token on the backend. Never send or trust a client-provided `user_id`.

### Statuses & Stages
- **Canonical Statuses**: `queued`, `processing`, `completed`, `failed`
- **Canonical Stages**: `loading_input`, `estimating_depth`, `fetching_reference`, `calibrating`, `packaging`, `validating_output`, `uploading_results`
- **Progress**: Backend-reported integer ($0–100$). Progress MUST NOT be estimated or calculated from elapsed time.

### Results & Artifacts
- **Result fields**: `job_id`, `output_type`, `artifacts`, `metadata`, `metrics`, `warnings`
- **Artifact fields**: `texture_url`, `heightmap_url`, `heightmap_16bit_url`, `confidence_map_url`, `dsm_url` (all artifact URLs are signed and optional).

### Contract Execution Rules
- If `dsm_url` exists, provide DSM access/download.
- If `dsm_url` is absent, present an explicit unavailable state.
- Missing metrics must be presented as unavailable ("N/A"), never 0.
- Never infer output semantics or format from filenames or file extensions.
- Relative elevation outputs (`output_type === "relative_dsm"`) MUST NEVER be labelled as metres ($m$).
- Do not assume heightmap encoding, bit depth, normalization, orientation, NoData values, or min/max elevation semantics without backend verification.

## Mock Development Mode
To allow full UI development while ML pipeline work is underway, frontend supports:
`VITE_USE_MOCK_API=true`

**Mock Mode Requirements**:
- Lives entirely inside `frontend/`.
- Preserves exact real API interfaces, method signatures, and TypeScript types.
- Simulates state transitions (`queued` → `processing` → `completed`) for development/demo only.
- Provides deterministic mock fixtures.
- Must never alter production backend behavior or leak mock paths into production API calls.
- Easy to disable via environment variable.
- UI components must never depend on mock-only fields.

## Supabase
- Supabase Auth manages identity and session persistence.
- Session access tokens are injected into API authorization headers.
- Never expose or include Supabase service-role keys in frontend code.
- Handle expired/invalid authentication sessions gracefully.

## Three.js
- Use Three.js strictly where spatial/terrain visualization requires 3D rendering.
- Viewer receives verified signed artifact URLs (`heightmap_url`, `texture_url`, `confidence_map_url`).
- Conceptual Viewer Pipeline:
  `heightmap_url` → decode image bytes → extract elevation values → normalize according to contract → terrain geometry → vertex displacement → calculate normals → map RGB texture → render scene.
- Keep Three.js lifecycle strictly isolated from React rendering lifecycle.
- **Disposal**: Explicitly dispose renderer, geometries, materials, textures, controls, and event listeners on unmount.
- Bounded vertex budget to avoid memory spikes.
- Handle window/container resize and WebGL context loss cleanly.
- Use Web Workers if heavy heightmap decoding or vertex array manipulation affects frame rates.

## Web Interface Guidelines
Apply accessibility and UI guidelines to all components:
- **Keyboard Operable**: Full keyboard navigation support (Tab, Enter, Space, Esc).
- **Focus Indicators**: Clear, visible focus indicators (`ring-2 ring-purple-600`).
- **Semantic HTML**: Proper HTML5 elements (`<header>`, `<main>`, `<section>`, `<nav>`, `<article>`, `<button>`).
- **Accessible Names & Labels**: Explicit labels, `aria-label`, and `aria-describedby` for form controls.
- **Hit Targets**: Minimum $44\times44\text{px}$ touch/click targets.
- **Form Controls**: Mobile input font $\ge 16\text{px}$ to prevent browser auto-zoom; never disable copy/paste or typing; disable submit button during active submission while keeping original label text visible alongside loading spinner.
- **Validation**: Place error messages adjacent to relevant fields; shift focus to the first invalid field upon validation failure.
- **Motion**: Respect `prefers-reduced-motion` settings.
- **Responsive Layout**: Fluid support across mobile, laptop, and ultra-wide viewports with zero horizontal overflow.
- **Status Communication**: Never rely solely on color to communicate status (use icons + text).
- **Page Titles & Numbers**: Tabular numbers for scientific metrics (`font-mono` / `tabular-nums`), accurate route document titles.

## Design Rules
The finalized Figma design is authoritative.
- Do NOT turn DepthWizard into a generic AI SaaS, generic dashboard, dark-mode site, glassmorphism interface, or neon-accented layout.
- **Preserved Aesthetic**:
  - Cream/light neutral canvas background (`#F6F4EC`)
  - Warm white surface containers (`#FDFCF8`)
  - Muted sage secondary surfaces (`#ECE9DD`)
  - Light green progress and active indicators (`#639A67` / `#DDEED9`)
  - Deep purple primary action buttons
  - Dark typography for contrast
  - Restrained borders & generous whitespace
  - Scientific spatial engineering visual character

## Testing
- Use Playwright for real browser-level flow verification.
- Priority paths: Auth, Upload/Input, Processing, Results, Error recovery, Responsive design, Keyboard navigation.
- Test user-visible outcomes and accessibility, not private implementation details.

## Git Safety
- Make small, reviewable changes.
- NEVER edit `backend/` or `ml/`.
- NEVER force-push or reset shared history.
- Inspect `git diff` before staging and committing.
- Commit ONLY `frontend/` changes.
- NEVER commit secrets or `.env` files.
