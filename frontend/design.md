# DepthWizard Visual Implementation Specification

This document defines the authoritative visual and UI design specification for DepthWizard, derived from the finalized Figma direction (`ai-context/05_FIGMA_FINAL_DIRECTION.md`).

---

## 1. Design Principles
- **Light Theme Only**: Cream and warm white foundation. No dark mode, neon glow, or glassmorphism.
- **Geospatial Engineering Aesthetic**: Clean, structured, scientific interface where 3D terrain visualization is the dominant visual focus.
- **Generous Whitespace & Restrained Borders**: Uncluttered layout, subtle borders, clear visual hierarchy.
- **Clear Information Architecture**: Distinguish clearly between relative depth outputs and calibrated metric DSMs.

---

## 2. Color Tokens
- **Canvas / Background**: `#F6F4EC` (Cream neutral canvas)
- **Surface / Card Background**: `#FDFCF8` (Warm white surface)
- **Secondary Surface / Track**: `#ECE9DD` (Muted sage surface)
- **Active Progress Fill**: `#639A67` (Light green progress fill)
- **Active Progress Substrate**: `#DDEED9` (Pale green highlight)
- **Primary Action (Buttons/CTAs)**: `#5B21B6` / `#6D28D9` (Deep purple primary action, hover `#4C1D95`)
- **Typography Primary**: `#111827` (Dark charcoal/black)
- **Typography Muted**: `#4B5563` (Muted slate text)
- **Borders**: `#E5E7EB` / `#D1D5DB` (Subtle, restrained gray/sage borders)
- **Error / Alert**: `#DC2626` (Red text/border), `#FEE2E2` (Light red fill)
- **Warning**: `#D97706` (Amber text/border), `#FEF3C7` (Light amber fill)

---

## 3. Typography
- **Font Family**: Inter, system-ui, sans-serif
- **Monospace / Metric Family**: JetBrains Mono, monospace (used for numerical metrics, coordinates, units, and tabular values)
- **Headings**:
  - `h1`: `text-2xl font-semibold tracking-tight text-gray-900`
  - `h2`: `text-xl font-medium tracking-tight text-gray-900`
  - `h3`: `text-lg font-medium text-gray-900`
- **Body Text**: `text-sm text-gray-700 leading-relaxed`
- **Caption / Meta**: `text-xs text-gray-500`

---

## 4. Spacing
- **Container Margins**: `px-4 sm:px-6 lg:px-8`
- **Grid Gaps**: `gap-4 sm:gap-6`
- **Card Padding**: `p-4 sm:p-6`
- **Element Spacing**: `space-y-4` / `space-y-6`

---

## 5. Borders
- **Standard Border**: `border border-gray-200`
- **Muted Sage Border**: `border border-[#ECE9DD]`
- **Active / Focused Border**: `border-purple-600 ring-2 ring-purple-600/20`

---

## 6. Radius
- **Buttons & Badges**: `rounded-md` ($6\text{px}$)
- **Cards & Viewports**: `rounded-lg` ($8\text{px}$)
- **Modal / Floating Panels**: `rounded-xl` ($12\text{px}$)

---

## 7. Shadows
- **Restrained Elevation**: `shadow-sm` for cards, `shadow-md` for floating viewer controls.
- No heavy, dark, or colored drop shadows.

---

## 8. Buttons
- **Primary Button**: Deep purple background (`bg-purple-700 hover:bg-purple-800 text-white font-medium px-4 py-2 rounded-md shadow-sm transition-colors`).
- **Secondary Button**: Muted sage / border variant (`bg-[#FDFCF8] hover:bg-[#ECE9DD] border border-gray-300 text-gray-800 font-medium px-4 py-2 rounded-md transition-colors`).
- **Destructive Button**: Crimson variant (`bg-red-600 hover:bg-red-700 text-white font-medium px-4 py-2 rounded-md transition-colors`).
- **Minimum Hit Target**: $44\times44\text{px}$ touch area.
- **Disabled State**: Opacity 50%, `cursor-not-allowed`, keeping label and loading spinner intact during submission.

---

## 9. Inputs & Form Controls
- **Style**: Warm white surface (`bg-[#FDFCF8] border border-gray-300 rounded-md px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-purple-600 focus:border-transparent`).
- **Font Size**: Minimum $16\text{px}$ (`text-base sm:text-sm`) on mobile devices to prevent automatic browser zoom.
- **Validation**: Error state displays crimson border (`border-red-500`) with helper text below.

---

## 10. Navigation
- **Top Header Bar**: Persistent navigation across all authenticated screens.
- **Links**: Clear text links with visible hover and active underline/highlight.

---

## 11. Header
- **Layout**: Full-width header on `#FDFCF8` background with subtle bottom border (`border-b border-gray-200`).
- **Left**: DepthWizard logo / branding mark ("DepthWizard").
- **Right**: Active session user email / profile status, Sign Out button.

---

## 12. Authentication Screen
- **Layout**: Centered warm surface card (`bg-[#FDFCF8]`) on cream canvas (`#F6F4EC`).
- **Content**: Product title, description, email/password form inputs, Supabase Auth submit button ("Sign In" / "Sign Up"), error message banner.
- **Behavior**: Preserves session state upon page refresh via Supabase Auth listener.

---

## 13. Input / Upload Screen
- **Upload Zone**: Centered drop area with dashed border (`border-2 border-dashed border-gray-300 hover:border-purple-500 rounded-xl p-8 bg-[#FDFCF8] text-center cursor-pointer transition-colors`).
- **Supported Formats Explanation**:
  - PNG, JPG / JPEG: Standard aerial/satellite imagery (produces relative elevation DSM).
  - TIFF / GeoTIFF: Spatial raster data (backend attempts reference calibration for absolute DSM in metres).
- **Action Button**: Primary purple CTA ("Process Image").
- **Persistent Footer**: Displayed ONLY on the Input screen (contains copyright, SIH 2026 attribution, and project metadata).

---

## 14. Processing Screen
- **Layout**: Centered card on cream canvas showing uploaded input image thumbnail.
- **Processing Stage Display**: Displays current backend-reported stage (`loading_input`, `estimating_depth`, `fetching_reference`, `calibrating`, `packaging`, `validating_output`, `uploading_results`).
- **Progress Indicator**: Muted sage track (`bg-[#ECE9DD]`) with partial light green fill (`bg-[#639A67]`).
- **Progress Rule**: Progress is driven strictly by backend percentage ($0–100\%$). Partial progress is displayed with a partial fill bar. Never displays 100% green until stage is fully completed.

---

## 15. Results Screen
- **Split Workspace Layout**:
  - **Left Side Panel (Width: 380px–440px on desktop)**:
    - Original RGB input thumbnail
    - Predicted depth / height map 2D thumbnail
    - Metadata panel (output type badge, height range, height units)
    - Scientific metrics panel (RMSE, MAE, Correlation — formatted in `font-mono tabular-nums`)
    - Warnings banner (e.g., calibration fallback warnings)
    - Download actions (DSM GeoTIFF download button when `dsm_url` exists)
  - **Right Main Panel (Flex-1)**: Large 3D Terrain Viewer.

---

## 16. Terrain Viewer (Three.js)
- **Viewport**: Dominates the spatial workspace area inside right panel (`w-full h-full min-h-[500px] rounded-lg overflow-hidden relative bg-[#111827]`).
- **3D Render**: Three.js WebGL canvas rendering 3D heightmap displacement geometry with original RGB texture overlay.
- **No Decorative Effects**: Clean spatial visualization; no artificial particle effects, neon grids, or unrequested 3D decorations.

---

## 17. Viewer Controls
- **Overlay Floating Controls Bar**: Positioned top-right or bottom-right inside the viewer container (`bg-[#FDFCF8]/90 backdrop-blur-sm border border-gray-200 shadow-md rounded-md p-1.5 flex items-center space-x-1`).
- **Controls**:
  - Rotate, Pan, Zoom tool buttons
  - Reset View button (resets camera position and orbit target)
  - DSM Representation toggle (switches between 3D Textured Terrain, 2D Heightmap, and Confidence Map if available).

---

## 18. Metadata Panel
- **Output Type Badge**:
  - `Absolute DSM`: Green badge (`bg-green-100 text-green-800 border-green-200`)
  - `Relative DSM`: Amber badge (`bg-amber-100 text-amber-800 border-amber-200`)
- **Elevation Range**: Displays `Min Height` and `Max Height` with explicit `height_units` ($m$ for absolute, $relative$ for relative).

---

## 19. Downloads Panel
- **Primary Download**: "Download DSM (GeoTIFF)" button.
- **Unavailable State**: If `dsm_url` is `null`, displays disabled state with text "DSM GeoTIFF unavailable for relative output".

---

## 20. Warnings Banner
- **Style**: Amber alert box (`bg-[#FEF3C7] border border-[#FDE68A] text-[#92400E] rounded-md p-3 text-sm flex items-start space-x-2`).
- **Content**: Renders warnings array from backend response (e.g., "SRTM reference fetch failed; falling back to relative elevation").

---

## 21. Empty States
- **Job History Empty State**: Clean card with text "No terrain processing jobs found. Upload an image to start."
- **Missing Metrics**: Displayed as "N/A" (never 0).

---

## 22. Loading States
- **Skeleton Loaders**: Stable `#ECE9DD` pulsing skeleton loaders for panels and thumbnails. No layout shift (CLS = 0).

---

## 23. Error States
- **API Error Banner**: Red alert container (`bg-[#FEE2E2] border border-[#FCA5A5] text-[#991B1B] rounded-md p-4 mb-4`).
- **Form Errors**: Inline error messages under invalid inputs with red border highlight.

---

## 24. Responsive Behavior
- **Desktop / Ultra-Wide ($\ge 1024\text{px}$)**: Side-by-side split layout (Left Summary Panel + Right 3D Terrain Viewer).
- **Tablet / Mobile ($< 1024\text{px}$)**: Stacks vertically (Summary Panel on top, full-width 3D Terrain Viewer below).

---

## 25. Accessibility (Web Interface Guidelines)
- **Keyboard Navigation**: All interactive elements (buttons, inputs, tabs, viewer controls) are keyboard operable.
- **Focus Rings**: `focus-visible:ring-2 focus-visible:ring-purple-600 focus-visible:ring-offset-2`.
- **Screen Reader Announcements**: Dynamic stage updates and errors use `aria-live="polite"` / `aria-live="assertive"`.
- **Text Contrast**: Dark text on light background satisfies WCAG 2.1 AA contrast ratio ($\ge 4.5:1$).

---

## 26. Motion & Animations
- **Transitions**: Subtle $150\text{ms}$ CSS transitions (`transition-colors duration-150 ease-in-out`) for hover and focus states.
- **Reduced Motion**: Under `@media (prefers-reduced-motion: reduce)`, all CSS transitions and smooth scrolling are disabled.
