import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { buildTerrainMesh, TerrainMeshBuildParams } from './TerrainMeshBuilder';
import { getSampleTerrain } from './sampleTerrainGenerator';

export type ViewMode = '3d' | '2d_heightmap' | 'confidence' | 'contour';
export type DisasterMode = 'before' | 'after' | 'difference';

export interface FlightTelemetry {
  altitude: number;
  headingDeg: number;
  speedMultiplier: number;
  coordX: number;
  coordZ: number;
  isFlying: boolean;
}

export class TerrainSceneManager {
  private container: HTMLElement;
  private scene: THREE.Scene;
  private camera: THREE.PerspectiveCamera;
  private renderer: THREE.WebGLRenderer;
  private controls: OrbitControls;

  private meshesByMode: Map<DisasterMode, THREE.Mesh> = new Map();
  private texturesByMode: Map<DisasterMode, THREE.Texture> = new Map();
  private heightmapsByMode: Map<DisasterMode, THREE.Texture> = new Map();
  private currentViewMode: ViewMode = '3d';
  private currentExaggeration: number = 2.2;

  private currentMesh: THREE.Mesh | null = null;
  private currentTexture: THREE.Texture | null = null;
  private heightmapTexture: THREE.Texture | null = null;
  private confidenceTexture: THREE.Texture | null = null;
  private afterTexture: THREE.Texture | null = null;
  private differenceTexture: THREE.Texture | null = null;
  private contourTexture: THREE.Texture | null = null;
  private currentDisasterMode: DisasterMode = 'before';
  private onTelemetryCallback: ((telemetry: FlightTelemetry) => void) | null = null;

  private animationFrameId: number | null = null;
  private resizeObserver: ResizeObserver | null = null;

  private initialCameraPosition = new THREE.Vector3(0, 7.5, 11);
  private initialTargetPosition = new THREE.Vector3(0, 0, 0);

  // Active clock for delta-timed keyboard flight movement
  private clock: THREE.Clock = new THREE.Clock();
  private pressedKeys = new Set<string>();

  constructor(container: HTMLElement) {
    this.container = container;

    // Scene with soft, clean architectural gallery gray backdrop
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color('#F1F5F9');

    // Camera
    const width = container.clientWidth || 800;
    const height = container.clientHeight || 500;
    this.camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 1000);
    this.camera.position.copy(this.initialCameraPosition);

    // Renderer
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    this.renderer.setSize(width, height);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;

    container.appendChild(this.renderer.domElement);

    // Controls
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.05;
    this.controls.maxPolarAngle = Math.PI / 2 - 0.02; // allows viewing pedestal side walls
    this.controls.target.copy(this.initialTargetPosition);

    // Prevent mouse wheel from scrolling the outer webpage
    this.renderer.domElement.addEventListener(
      'wheel',
      (e) => {
        e.preventDefault();
      },
      { passive: false }
    );

    // Keyboard flight navigation listeners
    window.addEventListener('keydown', this.handleKeyDown);
    window.addEventListener('keyup', this.handleKeyUp);
    window.addEventListener('blur', this.handleWindowBlur);

    // Lights
    this.setupLighting();

    // Resize observer
    this.setupResizeObserver();

    // Start render loop
    this.animate();
  }

  private setupLighting() {
    // Balanced ambient light suited for a soft gray backdrop
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.65);
    this.scene.add(ambientLight);

    // Warm directional sunlight casting distinct shadows across ridges
    const sunLight = new THREE.DirectionalLight(0xfffaee, 1.4);
    sunLight.position.set(16, 24, 14);
    sunLight.castShadow = true;
    sunLight.shadow.mapSize.width = 2048;
    sunLight.shadow.mapSize.height = 2048;
    sunLight.shadow.bias = -0.0003;
    // Fit shadow camera tightly around terrain diorama for sharp contact shadows
    sunLight.shadow.camera.near = 1;
    sunLight.shadow.camera.far = 65;
    sunLight.shadow.camera.left = -9;
    sunLight.shadow.camera.right = 9;
    sunLight.shadow.camera.top = 9;
    sunLight.shadow.camera.bottom = -9;
    this.scene.add(sunLight);

    // Cool fill light from opposite side for natural landscape illumination
    const fillLight = new THREE.DirectionalLight(0xdde3ec, 0.4);
    fillLight.position.set(-14, 12, -12);
    this.scene.add(fillLight);

    // Soft upward fill light to illuminate terrain base/underside, preventing harsh black shadows
    const bottomFillLight = new THREE.DirectionalLight(0xa5b4fc, 0.45);
    bottomFillLight.position.set(0, -18, 0);
    this.scene.add(bottomFillLight);
  }

  private setupResizeObserver() {
    this.resizeObserver = new ResizeObserver((entries) => {
      if (!entries.length) return;
      const { width, height } = entries[0].contentRect;
      if (width > 0 && height > 0) {
        this.camera.aspect = width / height;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(width, height);
      }
    });
    this.resizeObserver.observe(this.container);
  }

  public async loadTerrain(
    params: TerrainMeshBuildParams,
    _confidenceMapUrl?: string | null
  ): Promise<void> {
    this.clearCurrentMesh();

    const exaggeration = params.verticalExaggeration ?? 2.2;
    this.currentExaggeration = exaggeration;

    // 1. Build 'before' primary terrain model
    const beforeResult = await buildTerrainMesh({
      ...params,
      verticalExaggeration: this.currentExaggeration,
    });
    this.meshesByMode.set('before', beforeResult.mesh);
    this.texturesByMode.set('before', beforeResult.texture);

    // 2. Build 'after' sample terrain model (massive landslide & collapsed mountain flank)
    const afterSample = getSampleTerrain('after');
    const afterResult = await buildTerrainMesh({
      ...params,
      heightmapUrl: afterSample.heightmapUrl,
      textureUrl: afterSample.textureUrl,
      verticalExaggeration: this.currentExaggeration,
    });
    this.meshesByMode.set('after', afterResult.mesh);
    this.texturesByMode.set('after', afterResult.texture);

    // 3. Build 'difference' sample terrain model (delta displacement elevation + chromatic heatmap)
    const diffSample = getSampleTerrain('difference');
    const diffResult = await buildTerrainMesh({
      ...params,
      heightmapUrl: diffSample.heightmapUrl,
      textureUrl: diffSample.textureUrl,
      verticalExaggeration: this.currentExaggeration,
    });
    this.meshesByMode.set('difference', diffResult.mesh);
    this.texturesByMode.set('difference', diffResult.texture);

    // Texture loader for overlays & slope view
    const textureLoader = new THREE.TextureLoader();
    const loadTex = (url: string): Promise<THREE.Texture> => {
      if (url.startsWith('http')) {
        textureLoader.setCrossOrigin('anonymous');
      }
      return new Promise((resolve) => {
        textureLoader.load(
          url,
          (tex) => {
            tex.colorSpace = THREE.SRGBColorSpace;
            tex.wrapS = THREE.ClampToEdgeWrapping;
            tex.wrapT = THREE.ClampToEdgeWrapping;
            resolve(tex);
          },
          undefined,
          () => resolve(beforeResult.texture)
        );
      });
    };

    const beforeHmap = await loadTex(params.heightmapUrl || getSampleTerrain('before').heightmapUrl);
    const afterHmap = await loadTex(afterSample.heightmapUrl);
    const diffHmap = await loadTex(diffSample.heightmapUrl);

    this.heightmapsByMode.set('before', beforeHmap);
    this.heightmapsByMode.set('after', afterHmap);
    this.heightmapsByMode.set('difference', diffHmap);

    // Set initial active mesh
    const activeMesh = this.meshesByMode.get(this.currentDisasterMode) || beforeResult.mesh;
    this.currentMesh = activeMesh;
    this.scene.add(this.currentMesh);

    // Backwards-compatibility references
    this.currentTexture = beforeResult.texture;
    this.heightmapTexture = beforeHmap;
    this.afterTexture = afterResult.texture;
    this.differenceTexture = diffResult.texture;

    this.applyViewMode(this.currentViewMode);
    this.resetView();
  }

  public setDisasterMode(mode: DisasterMode): void {
    this.currentDisasterMode = mode;
    const targetMesh = this.meshesByMode.get(mode);
    if (!targetMesh) return;

    if (this.currentMesh && this.currentMesh !== targetMesh) {
      this.scene.remove(this.currentMesh);
    }
    this.currentMesh = targetMesh;
    if (!this.scene.children.includes(this.currentMesh)) {
      this.scene.add(this.currentMesh);
    }

    this.applyViewMode(this.currentViewMode);
  }

  public setViewMode(mode: ViewMode): void {
    this.currentViewMode = mode;
    this.applyViewMode(mode);
  }

  private applyViewMode(mode: ViewMode): void {
    if (!this.currentMesh) return;
    const materials = Array.isArray(this.currentMesh.material)
      ? this.currentMesh.material
      : [this.currentMesh.material];
    const terrainMat = materials[0] as THREE.MeshStandardMaterial;

    if (mode === '2d_heightmap') {
      const hmap = this.heightmapsByMode.get(this.currentDisasterMode) || this.heightmapTexture;
      if (hmap) terrainMat.map = hmap;
    } else {
      const tex = this.texturesByMode.get(this.currentDisasterMode) || this.currentTexture;
      if (tex) terrainMat.map = tex;
    }

    terrainMat.needsUpdate = true;
  }

  public setHeightExaggeration(multiplier: number): void {
    this.currentExaggeration = multiplier;
    this.meshesByMode.forEach((mesh) => {
      const geom = mesh.geometry;
      const rawHeights = geom.userData.rawHeights as Float32Array | undefined;
      const isSkirt = geom.userData.isSkirt as Uint8Array | undefined;
      const minRawZ = (geom.userData.minRawZ as number) ?? 0;
      if (!rawHeights || !isSkirt) return;

      const currentZBase = (minRawZ * multiplier) - 0.8;
      const posAttr = geom.attributes.position;
      for (let i = 0; i < posAttr.count; i++) {
        const type = isSkirt[i];
        if (type === 2) {
          posAttr.setZ(i, currentZBase);
        } else {
          posAttr.setZ(i, rawHeights[i] * multiplier);
        }
      }
      posAttr.needsUpdate = true;
      geom.computeVertexNormals();
    });
  }

  public setTelemetryCallback(cb: ((telemetry: FlightTelemetry) => void) | null): void {
    this.onTelemetryCallback = cb;
  }

  private handleKeyDown = (e: KeyboardEvent) => {
    const target = e.target as HTMLElement | null;
    if (target && ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)) return;

    const flightCodes = [
      'KeyW',
      'KeyS',
      'KeyA',
      'KeyD',
      'KeyQ',
      'KeyE',
      'KeyC',
      'Space',
      'ArrowUp',
      'ArrowDown',
      'ArrowLeft',
      'ArrowRight',
      'ShiftLeft',
      'ShiftRight',
    ];
    const flightKeys = [
      'w',
      's',
      'a',
      'd',
      'q',
      'e',
      'c',
      ' ',
      'arrowup',
      'arrowdown',
      'arrowleft',
      'arrowright',
    ];

    // Prevent default browser actions (such as window scrolling when W/S/Arrows/Space pressed)
    if (flightCodes.includes(e.code) || flightKeys.includes(e.key.toLowerCase())) {
      e.preventDefault();
    }
    this.pressedKeys.add(e.code);
  };

  private handleKeyUp = (e: KeyboardEvent) => {
    this.pressedKeys.delete(e.code);
  };

  private handleWindowBlur = () => {
    this.pressedKeys.clear();
  };

  public stopFlythrough(): void {
    // Backwards-compatibility stub
  }

  public getIsFlying(): boolean {
    return false;
  }

  public resetView(): void {
    this.camera.position.copy(this.initialCameraPosition);
    this.controls.target.copy(this.initialTargetPosition);
    this.controls.update();
  }

  private animate = () => {
    this.animationFrameId = requestAnimationFrame(this.animate);

    const delta = Math.min(this.clock.getDelta(), 0.1);

    if (this.pressedKeys.size > 0) {
      const isSprinting = this.pressedKeys.has('ShiftLeft') || this.pressedKeys.has('ShiftRight');
      const baseSpeed = 7.0;
      const speed = isSprinting ? baseSpeed * 2.2 : baseSpeed;
      const moveDist = speed * delta;

      const forward = new THREE.Vector3();
      this.camera.getWorldDirection(forward);
      forward.y = 0;
      if (forward.lengthSq() > 0.0001) {
        forward.normalize();
      }

      const right = new THREE.Vector3().crossVectors(forward, this.camera.up).normalize();
      const moveDelta = new THREE.Vector3(0, 0, 0);

      if (this.pressedKeys.has('KeyW') || this.pressedKeys.has('ArrowUp')) moveDelta.add(forward);
      if (this.pressedKeys.has('KeyS') || this.pressedKeys.has('ArrowDown')) moveDelta.sub(forward);
      if (this.pressedKeys.has('KeyD') || this.pressedKeys.has('ArrowRight')) moveDelta.add(right);
      if (this.pressedKeys.has('KeyA') || this.pressedKeys.has('ArrowLeft')) moveDelta.sub(right);
      if (this.pressedKeys.has('KeyE') || this.pressedKeys.has('Space')) moveDelta.y += 1.0;
      if (this.pressedKeys.has('KeyQ') || this.pressedKeys.has('KeyC')) moveDelta.y -= 1.0;

      if (moveDelta.lengthSq() > 0.0001) {
        moveDelta.normalize().multiplyScalar(moveDist);
        this.camera.position.add(moveDelta);
        // Prevent camera from dipping below the base pedestal floor
        this.camera.position.y = Math.max(0.4, this.camera.position.y);
        this.controls.target.add(moveDelta);
      }
    }

    this.controls.update();

    // Emit live tactical flight telemetry
    if (this.onTelemetryCallback) {
      const dx = this.camera.position.x - this.controls.target.x;
      const dz = this.camera.position.z - this.controls.target.z;
      const rad = Math.atan2(dx, dz);
      const headingDeg = Math.round(((rad * 180 / Math.PI) + 360) % 360);
      const altitude = Math.max(10, Math.round(this.camera.position.y * 28));
      const isSprinting = this.pressedKeys.has('ShiftLeft') || this.pressedKeys.has('ShiftRight');

      this.onTelemetryCallback({
        altitude,
        headingDeg,
        speedMultiplier: isSprinting ? 2.2 : 1.0,
        coordX: Math.round(this.camera.position.x * 10) / 10,
        coordZ: Math.round(this.camera.position.z * 10) / 10,
        isFlying: this.pressedKeys.size > 0,
      });
    }

    this.renderer.render(this.scene, this.camera);
  };


  private clearCurrentMesh() {
    this.meshesByMode.forEach((mesh) => {
      this.scene.remove(mesh);
      if (mesh.geometry) mesh.geometry.dispose();
      if (Array.isArray(mesh.material)) {
        mesh.material.forEach((m) => m.dispose());
      } else if (mesh.material) {
        mesh.material.dispose();
      }
    });
    this.meshesByMode.clear();
    this.currentMesh = null;

    this.texturesByMode.forEach((t) => t.dispose());
    this.texturesByMode.clear();
    this.heightmapsByMode.forEach((t) => t.dispose());
    this.heightmapsByMode.clear();

    if (this.currentTexture) {
      this.currentTexture.dispose();
      this.currentTexture = null;
    }
    if (this.heightmapTexture) {
      this.heightmapTexture.dispose();
      this.heightmapTexture = null;
    }
    if (this.confidenceTexture) {
      this.confidenceTexture.dispose();
      this.confidenceTexture = null;
    }
    if (this.afterTexture) {
      this.afterTexture.dispose();
      this.afterTexture = null;
    }
    if (this.differenceTexture) {
      this.differenceTexture.dispose();
      this.differenceTexture = null;
    }
    if (this.contourTexture) {
      this.contourTexture.dispose();
      this.contourTexture = null;
    }
  }

  public dispose(): void {
    if (this.animationFrameId !== null) {
      cancelAnimationFrame(this.animationFrameId);
    }

    window.removeEventListener('keydown', this.handleKeyDown);
    window.removeEventListener('keyup', this.handleKeyUp);
    window.removeEventListener('blur', this.handleWindowBlur);
    this.pressedKeys.clear();

    if (this.resizeObserver) {
      this.resizeObserver.disconnect();
    }

    this.clearCurrentMesh();

    if (this.currentTexture) this.currentTexture.dispose();
    if (this.heightmapTexture) this.heightmapTexture.dispose();
    if (this.confidenceTexture) this.confidenceTexture.dispose();
    if (this.afterTexture) this.afterTexture.dispose();
    if (this.differenceTexture) this.differenceTexture.dispose();
    if (this.contourTexture) this.contourTexture.dispose();

    this.controls.dispose();
    this.renderer.dispose();

    if (this.container && this.renderer.domElement) {
      this.container.removeChild(this.renderer.domElement);
    }
  }
}
