import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';

// Stylized river cross-section — NOT a bathymetric reconstruction. Per
// docs/phase_river_silt.md and explicit product direction: the goal is a
// side view that reads clearly as "river channel, water, sediment build-up
// on the bed," preserving the real image-derived channel skeleton
// (cross_section_profile from ml/river_silt_pipeline.py), not literal 1:1
// depth accuracy. Shorter/simpler than TerrainSceneManager on purpose —
// this scene has no textures, no flight controls, no disaster modes.

const CHANNEL_WIDTH = 10;
const CHANNEL_DEPTH = 2.4; // max bed depth below the water line
const WATER_LEVEL = 0;
const EXTRUDE_DEPTH = 1.6; // Z-thickness, gives the channel a solid 3D look without real volumetric data

const COLOR_WATER = new THREE.Color(0x4f8fc7);
const COLOR_SEDIMENT = new THREE.Color(0x8a6a44);
// Murky transitional color at the sediment/water boundary, not a hard
// line — a real turbid riverbed doesn't have a crisp edge where silt ends
// and clear water begins.
const COLOR_BOUNDARY = COLOR_SEDIMENT.clone().lerp(COLOR_WATER, 0.4);
const COLOR_BED_LINE = 0x3a362c;
const COLOR_BACKGROUND = '#dfe4ea';

// Real per-pixel image variation is jagged at 48 samples — a real riverbed
// (and especially a settled sediment layer) is smoother than that. A small
// moving average removes sample-to-sample noise while keeping the real
// overall shape, instead of literally mirroring every bump.
function smooth(values: number[], window = 5): number[] {
  const half = Math.floor(window / 2);
  return values.map((_, i) => {
    let sum = 0;
    let count = 0;
    for (let k = -half; k <= half; k++) {
      const j = i + k;
      if (j >= 0 && j < values.length) {
        sum += values[j];
        count += 1;
      }
    }
    return sum / count;
  });
}

export class SiltCrossSectionScene {
  private container: HTMLElement;
  private scene: THREE.Scene;
  private camera: THREE.PerspectiveCamera;
  private renderer: THREE.WebGLRenderer;
  private controls: OrbitControls;
  private animationFrameId: number | null = null;
  private resizeObserver: ResizeObserver | null = null;
  private group: THREE.Group | null = null;

  constructor(container: HTMLElement) {
    this.container = container;

    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(COLOR_BACKGROUND);
    this.scene.fog = new THREE.Fog(new THREE.Color(COLOR_BACKGROUND).getHex(), 10, 22);

    const width = container.clientWidth || 600;
    const height = container.clientHeight || 360;
    this.camera = new THREE.PerspectiveCamera(40, width / height, 0.1, 100);
    this.camera.position.set(0, 2.4, 10);

    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    this.renderer.setSize(width, height);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    container.appendChild(this.renderer.domElement);

    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.minPolarAngle = Math.PI / 2 - 0.5;
    this.controls.maxPolarAngle = Math.PI / 2 + 0.3; // keep it a "side view" — limited tilt, not free orbit
    // Unbounded scroll-to-zoom previously let the camera clip inside a bank
    // mesh — clamp so the channel always stays framed.
    this.controls.minDistance = 4;
    this.controls.maxDistance = 16;
    this.controls.target.set(0, -CHANNEL_DEPTH / 2, 0);
    this.controls.update();

    this.renderer.domElement.addEventListener('wheel', (e) => e.preventDefault(), { passive: false });

    // Hemisphere light (sky/ground tint) + one directional key light reads
    // far more like a real outdoor scene than flat ambient + one direct.
    const hemi = new THREE.HemisphereLight(0xcfe0f2, 0x4a3f2f, 0.9);
    const sun = new THREE.DirectionalLight(0xfff6e6, 1.0);
    sun.position.set(5, 8, 6);
    sun.castShadow = true;
    sun.shadow.mapSize.set(1024, 1024);
    const shadowCam = sun.shadow.camera as THREE.OrthographicCamera;
    shadowCam.left = -CHANNEL_WIDTH;
    shadowCam.right = CHANNEL_WIDTH;
    shadowCam.top = 4;
    shadowCam.bottom = -CHANNEL_DEPTH * 2;
    shadowCam.near = 1;
    shadowCam.far = 20;
    sun.shadow.bias = -0.002;
    const fill = new THREE.DirectionalLight(0xaeccee, 0.25);
    fill.position.set(-6, 3, -4);
    this.scene.add(hemi, sun, fill);

    this.setupResizeObserver();
    this.animate = this.animate.bind(this);
    this.animate();
  }

  private setupResizeObserver() {
    this.resizeObserver = new ResizeObserver(() => {
      const width = this.container.clientWidth;
      const height = this.container.clientHeight;
      if (width === 0 || height === 0) return;
      this.camera.aspect = width / height;
      this.camera.updateProjectionMatrix();
      this.renderer.setSize(width, height);
    });
    this.resizeObserver.observe(this.container);
  }

  /**
   * profile: cross_section_profile from the pipeline, 0-1 normalized real
   * per-pixel image variation. sedimentIntensity: 0-1, derived from
   * predicted SSC relative to the heatmap's own normalization ceiling —
   * higher = thicker sediment layer, less remaining water depth (the
   * visual proxy for "capacity lost to siltation").
   */
  public build(profile: number[], sedimentIntensity: number): void {
    this.clear();
    const group = new THREE.Group();
    const n = Math.max(profile.length, 2);
    const smoothed = smooth(profile);
    const xStep = CHANNEL_WIDTH / (n - 1);

    // Real, image-derived skeleton (smoothed) layered onto a parabolic
    // channel base (deepest mid-channel, shallow at the banks) — same
    // "stylized but grounded in real signal" honesty as the heatmap.
    const bedY = smoothed.map((v, i) => {
      const x = i / (n - 1);
      const parabola = Math.sin(Math.PI * x); // 0 at banks, 1 at mid-channel
      const skeleton = 0.55 + 0.45 * v; // real per-pixel variation, never fully flattens the shape
      return -CHANNEL_DEPTH * parabola * skeleton;
    });

    // Sediment sits as a settled layer along the bottom — a gently
    // undulating boundary (mostly a function of the intensity level, only
    // lightly modulated by the real signal), not a shape that mirrors
    // every bump of the bed. Physically: sediment deposits fill in the low
    // spots and smooth the bed out, they don't amplify its noise.
    const sedimentTopY = bedY.map((bed, i) => {
      const local = 0.9 + 0.2 * smoothed[i]; // small real-signal modulation only
      const thickness = Math.max(0, Math.min(-bed, CHANNEL_DEPTH * sedimentIntensity * local));
      return bed + thickness;
    });

    group.add(this.buildChannel(bedY, sedimentTopY, xStep));
    group.add(this.buildBedLine(bedY, xStep));
    group.add(this.buildWaterSurface(xStep, n));

    this.group = group;
    this.scene.add(group);
  }

  /**
   * A thin, glossy, semi-transparent ribbon riding just above the solid
   * channel's water-color top surface — a static shine, not an animated
   * ripple. Purely decorative overlay; the solid mesh underneath (with the
   * real sediment/water gradient) is untouched.
   */
  private buildWaterSurface(xStep: number, n: number): THREE.Mesh {
    const positions: number[] = [];
    const indices: number[] = [];
    for (let i = 0; i < n; i++) {
      const x = -CHANNEL_WIDTH / 2 + i * xStep;
      positions.push(x, WATER_LEVEL + 0.02, 0.05, x, WATER_LEVEL + 0.02, -EXTRUDE_DEPTH - 0.05);
    }
    for (let i = 0; i < n - 1; i++) {
      const a = i * 2, b = (i + 1) * 2;
      indices.push(a, a + 1, b, b, a + 1, b + 1);
      indices.push(a, b, a + 1, a + 1, b, b + 1); // back face, visible from below too
    }

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
    geometry.setIndex(indices);
    geometry.computeVertexNormals();
    const material = new THREE.MeshStandardMaterial({
      color: COLOR_WATER,
      transparent: true,
      opacity: 0.5,
      roughness: 0.05,
      metalness: 0.15,
      side: THREE.DoubleSide,
    });
    return new THREE.Mesh(geometry, material);
  }

  /**
   * One fully solid, closed mesh spanning bedY (sediment color) up through
   * sedimentTopY (murky boundary color) to the water line (water color) —
   * vertex colors interpolate smoothly across each face, giving a real
   * gradient instead of two flat-colored layers meeting at a hard edge.
   * Closed on every side (front/back walls, top, bottom, and end caps) so
   * there is no open/hollow interior visible from any angle.
   */
  private buildChannel(bedY: number[], sedimentTopY: number[], xStep: number): THREE.Mesh {
    const n = bedY.length;
    const levelYs = (i: number) => [bedY[i], sedimentTopY[i], WATER_LEVEL];
    const levelColors = [COLOR_SEDIMENT, COLOR_BOUNDARY, COLOR_WATER];

    const positions: number[] = [];
    const colors: number[] = [];
    // vertexIndex(i, level, z) -> index into positions/colors, z: 0=front, 1=back
    const stride = 6; // 3 levels x 2 depths per column
    const idx = (i: number, level: number, z: number) => i * stride + level * 2 + z;

    for (let i = 0; i < n; i++) {
      const x = -CHANNEL_WIDTH / 2 + i * xStep;
      const ys = levelYs(i);
      for (let level = 0; level < 3; level++) {
        const c = levelColors[level];
        positions.push(x, ys[level], 0); // front
        colors.push(c.r, c.g, c.b);
        positions.push(x, ys[level], -EXTRUDE_DEPTH); // back
        colors.push(c.r, c.g, c.b);
      }
    }

    const indices: number[] = [];
    for (let i = 0; i < n - 1; i++) {
      for (let level = 0; level < 2; level++) {
        const a0 = idx(i, level, 0), a1 = idx(i, level + 1, 0);
        const b0 = idx(i + 1, level, 0), b1 = idx(i + 1, level + 1, 0);
        const a0z = idx(i, level, 1), a1z = idx(i, level + 1, 1);
        const b0z = idx(i + 1, level, 1), b1z = idx(i + 1, level + 1, 1);
        // front wall segment
        indices.push(a0, a1, b0, b0, a1, b1);
        // back wall segment (reversed winding)
        indices.push(a0z, b0z, a1z, b1z, a1z, b0z);
      }
      // bottom cap (bedY, level 0) and top cap (water line, level 2)
      const aBotF = idx(i, 0, 0), aBotB = idx(i, 0, 1);
      const bBotF = idx(i + 1, 0, 0), bBotB = idx(i + 1, 0, 1);
      indices.push(aBotF, bBotF, aBotB, bBotB, aBotB, bBotF);
      const aTopF = idx(i, 2, 0), aTopB = idx(i, 2, 1);
      const bTopF = idx(i + 1, 2, 0), bTopB = idx(i + 1, 2, 1);
      indices.push(aTopF, aTopB, bTopF, bTopF, aTopB, bTopB);
    }
    // end caps (i=0 and i=n-1) — otherwise the channel is open at both ends
    for (const [i, flip] of [[0, false], [n - 1, true]] as [number, boolean][]) {
      for (let level = 0; level < 2; level++) {
        const f0 = idx(i, level, 0), f1 = idx(i, level + 1, 0);
        const z0 = idx(i, level, 1), z1 = idx(i, level + 1, 1);
        if (!flip) indices.push(f0, z0, f1, f1, z0, z1);
        else indices.push(f0, f1, z0, f1, z1, z0);
      }
    }

    // Expand to non-indexed: walls, top/bottom caps, and end caps share
    // vertices at their seams above, but those faces point in very
    // different directions. computeVertexNormals() on an indexed geometry
    // averages normals across every face touching a shared vertex — real
    // bug found here: that averaging blended a vertical wall's outward
    // normal with a horizontal cap's up/down normal at every shared edge,
    // producing wrong, muddy lighting (the mesh rendered almost black).
    // Duplicating vertices per-triangle (no shared index buffer) gives
    // each triangle its own correct flat normal instead.
    const flatPositions: number[] = [];
    const flatColors: number[] = [];
    for (const vertexIndex of indices) {
      flatPositions.push(positions[vertexIndex * 3], positions[vertexIndex * 3 + 1], positions[vertexIndex * 3 + 2]);
      flatColors.push(colors[vertexIndex * 3], colors[vertexIndex * 3 + 1], colors[vertexIndex * 3 + 2]);
    }

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(flatPositions, 3));
    geometry.setAttribute('color', new THREE.Float32BufferAttribute(flatColors, 3));
    geometry.computeVertexNormals();
    const material = new THREE.MeshStandardMaterial({
      vertexColors: true,
      side: THREE.DoubleSide,
      roughness: 0.75,
      metalness: 0.0,
      flatShading: true,
    });
    const mesh = new THREE.Mesh(geometry, material);
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    return mesh;
  }

  private buildBedLine(bedY: number[], xStep: number): THREE.Line {
    const n = bedY.length;
    const positions: number[] = [];
    for (let i = 0; i < n; i++) {
      const x = -CHANNEL_WIDTH / 2 + i * xStep;
      positions.push(x, bedY[i] - 0.03, -EXTRUDE_DEPTH / 2);
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
    const material = new THREE.LineBasicMaterial({ color: COLOR_BED_LINE, linewidth: 2, transparent: true, opacity: 0.5 });
    return new THREE.Line(geometry, material); // riverbed outline, purely decorative
  }

  private clear(): void {
    if (!this.group) return;
    this.group.traverse((obj) => {
      if (obj instanceof THREE.Mesh || obj instanceof THREE.Line) {
        obj.geometry.dispose();
        const mat = obj.material;
        if (Array.isArray(mat)) mat.forEach((m) => m.dispose());
        else mat.dispose();
      }
    });
    this.scene.remove(this.group);
    this.group = null;
  }

  private animate(): void {
    this.animationFrameId = requestAnimationFrame(this.animate);
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
  }

  public dispose(): void {
    if (this.animationFrameId !== null) cancelAnimationFrame(this.animationFrameId);
    this.resizeObserver?.disconnect();
    this.clear();
    this.controls.dispose();
    this.renderer.dispose();
    if (this.renderer.domElement.parentElement === this.container) {
      this.container.removeChild(this.renderer.domElement);
    }
  }
}
