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
const CHANNEL_DEPTH = 2.4; // max bed depth below the bank-top water line
const WATER_LEVEL = 0; // bank-top, fixed reference
const EXTRUDE_DEPTH = 1.4; // Z-thickness, gives the ribbon a 3D look without real volumetric data

const COLOR_WATER = 0x5e9fd4;
const COLOR_SEDIMENT = 0x8a6a44;
const COLOR_BED = 0x4a4638;
const COLOR_BANK = 0x6b8f5a;

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
    this.scene.background = new THREE.Color('#e2e6eb');

    const width = container.clientWidth || 600;
    const height = container.clientHeight || 360;
    this.camera = new THREE.PerspectiveCamera(40, width / height, 0.1, 100);
    this.camera.position.set(0, 2.2, 9);

    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    this.renderer.setSize(width, height);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.appendChild(this.renderer.domElement);

    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.minPolarAngle = Math.PI / 2 - 0.5;
    this.controls.maxPolarAngle = Math.PI / 2 + 0.3; // keep it a "side view" — limited tilt, not free orbit
    this.controls.target.set(0, -CHANNEL_DEPTH / 2, 0);
    this.controls.update();

    this.renderer.domElement.addEventListener('wheel', (e) => e.preventDefault(), { passive: false });

    const ambient = new THREE.AmbientLight(0xffffff, 0.7);
    const dir = new THREE.DirectionalLight(0xffffff, 0.8);
    dir.position.set(4, 6, 5);
    this.scene.add(ambient, dir);

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
    const xStep = CHANNEL_WIDTH / (n - 1);

    // Real, image-derived skeleton (profile) layered onto a parabolic
    // channel base (deepest mid-channel, shallow at the banks) — same
    // "stylized but grounded in real signal" honesty as the heatmap.
    const bedY = profile.map((v, i) => {
      const x = i / (n - 1);
      const parabola = Math.sin(Math.PI * x); // 0 at banks, 1 at mid-channel
      const skeleton = 0.5 + 0.5 * v; // real per-pixel variation, never fully flattens the shape
      return -CHANNEL_DEPTH * parabola * skeleton;
    });

    const sedimentTopY = bedY.map((bed, i) => {
      const local = 0.6 + 0.4 * profile[i]; // local thickness variation, still grounded in real signal
      const thickness = Math.min(-bed, CHANNEL_DEPTH * sedimentIntensity * local);
      return bed + thickness;
    });

    group.add(this.buildRibbon(bedY, sedimentTopY, xStep, COLOR_SEDIMENT, 0));
    group.add(this.buildRibbon(sedimentTopY, bedY.map(() => WATER_LEVEL), xStep, COLOR_WATER, 0.55));
    group.add(this.buildFloor(bedY, xStep));
    group.add(this.buildBanks());

    this.group = group;
    this.scene.add(group);
  }

  private buildRibbon(bottomY: number[], topY: number[], xStep: number, color: number, opacity: number): THREE.Mesh {
    const n = bottomY.length;
    const positions: number[] = [];
    const indices: number[] = [];
    for (let i = 0; i < n; i++) {
      const x = -CHANNEL_WIDTH / 2 + i * xStep;
      // front face (z=0) and back face (z=-EXTRUDE_DEPTH), bottom then top each
      positions.push(x, bottomY[i], 0, x, topY[i], 0, x, bottomY[i], -EXTRUDE_DEPTH, x, topY[i], -EXTRUDE_DEPTH);
    }
    for (let i = 0; i < n - 1; i++) {
      const a = i * 4, b = (i + 1) * 4;
      // front quad
      indices.push(a, a + 1, b, b, a + 1, b + 1);
      // back quad
      indices.push(a + 2, b + 2, a + 3, b + 3, a + 3, b + 2);
      // top quad (connecting front/back at topY)
      indices.push(a + 1, a + 3, b + 1, b + 1, a + 3, b + 3);
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
    geometry.setIndex(indices);
    geometry.computeVertexNormals();
    const material = new THREE.MeshStandardMaterial({
      color,
      transparent: opacity < 1,
      opacity,
      side: THREE.DoubleSide,
      roughness: 0.85,
    });
    return new THREE.Mesh(geometry, material);
  }

  private buildFloor(bedY: number[], xStep: number): THREE.Line {
    const n = bedY.length;
    const positions: number[] = [];
    for (let i = 0; i < n; i++) {
      const x = -CHANNEL_WIDTH / 2 + i * xStep;
      positions.push(x, bedY[i] - 0.05, -EXTRUDE_DEPTH / 2);
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
    const material = new THREE.LineBasicMaterial({ color: COLOR_BED, linewidth: 2 });
    return new THREE.Line(geometry, material); // riverbed outline, purely decorative
  }

  private buildBanks(): THREE.Group {
    const group = new THREE.Group();
    const bankGeo = new THREE.BoxGeometry(1.2, 0.6, EXTRUDE_DEPTH);
    const bankMat = new THREE.MeshStandardMaterial({ color: COLOR_BANK, roughness: 0.9 });
    const left = new THREE.Mesh(bankGeo, bankMat);
    left.position.set(-CHANNEL_WIDTH / 2 - 0.5, WATER_LEVEL + 0.3, -EXTRUDE_DEPTH / 2);
    const right = left.clone();
    right.position.x = CHANNEL_WIDTH / 2 + 0.5;
    group.add(left, right);
    return group;
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
