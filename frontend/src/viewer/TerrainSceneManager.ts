import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { buildTerrainMesh, TerrainMeshBuildParams } from './TerrainMeshBuilder';

export type ViewMode = '3d' | '2d_heightmap' | 'confidence';

export class TerrainSceneManager {
  private container: HTMLElement;
  private scene: THREE.Scene;
  private camera: THREE.PerspectiveCamera;
  private renderer: THREE.WebGLRenderer;
  private controls: OrbitControls;

  private currentMesh: THREE.Mesh | null = null;
  private currentTexture: THREE.Texture | null = null;
  private heightmapTexture: THREE.Texture | null = null;
  private confidenceTexture: THREE.Texture | null = null;

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
    this.scene.background = new THREE.Color('#e2e6eb');

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
    confidenceMapUrl?: string | null
  ): Promise<void> {
    this.clearCurrentMesh();

    const buildResult = await buildTerrainMesh(params);
    this.currentMesh = buildResult.mesh;
    this.currentTexture = buildResult.texture;

    this.scene.add(this.currentMesh);

    // Texture loader for overlays
    const textureLoader = new THREE.TextureLoader();

    // Load 2D heightmap texture overlay for mode switching
    if (params.heightmapUrl.startsWith('http')) {
      textureLoader.setCrossOrigin('anonymous');
    }

    this.heightmapTexture = await new Promise<THREE.Texture>((resolve) => {
      textureLoader.load(
        params.heightmapUrl,
        (tex) => {
          tex.colorSpace = THREE.SRGBColorSpace;
          tex.wrapS = THREE.ClampToEdgeWrapping;
          tex.wrapT = THREE.ClampToEdgeWrapping;
          resolve(tex);
        },
        undefined,
        () => resolve(buildResult.texture) // fallback to main texture on error
      );
    });

    // Load confidence texture overlay if confidenceMapUrl is provided
    const effectiveConfidenceUrl =
      confidenceMapUrl ?? (params as { confidenceMapUrl?: string | null }).confidenceMapUrl;
    if (effectiveConfidenceUrl) {
      if (effectiveConfidenceUrl.startsWith('http')) {
        textureLoader.setCrossOrigin('anonymous');
      }

      this.confidenceTexture = await new Promise<THREE.Texture | null>((resolve) => {
        textureLoader.load(
          effectiveConfidenceUrl,
          (tex) => {
            tex.colorSpace = THREE.SRGBColorSpace;
            resolve(tex);
          },
          undefined,
          (err) => {
            console.warn('Failed to load confidence map texture:', err);
            resolve(null);
          }
        );
      });
    } else {
      this.confidenceTexture = null;
    }

    this.resetView();
  }

  public setViewMode(mode: ViewMode): void {
    if (!this.currentMesh) return;
    const materials = Array.isArray(this.currentMesh.material)
      ? this.currentMesh.material
      : [this.currentMesh.material];
    const terrainMat = materials[0] as THREE.MeshStandardMaterial;

    if (mode === '3d') {
      if (this.currentTexture) terrainMat.map = this.currentTexture;
    } else if (mode === '2d_heightmap') {
      if (this.heightmapTexture) terrainMat.map = this.heightmapTexture;
    } else if (mode === 'confidence') {
      if (this.confidenceTexture) {
        terrainMat.map = this.confidenceTexture;
      } else if (this.currentTexture) {
        terrainMat.map = this.currentTexture;
      }
    }

    terrainMat.needsUpdate = true;
  }

  public setHeightExaggeration(multiplier: number): void {
    if (!this.currentMesh) return;
    const geom = this.currentMesh.geometry;
    const rawHeights = geom.userData.rawHeights as Float32Array | undefined;
    const isSkirt = geom.userData.isSkirt as Uint8Array | undefined;
    const minRawZ = (geom.userData.minRawZ as number) ?? 0;
    if (!rawHeights || !isSkirt) return;

    // Dynamically anchor base floor below the lowest displaced point
    const currentZBase = (minRawZ * multiplier) - 0.8;

    const posAttr = geom.attributes.position;
    for (let i = 0; i < posAttr.count; i++) {
      const type = isSkirt[i];
      if (type === 2) {
        // Bottom floor and bottom skirt vertices stay anchored at currentZBase
        posAttr.setZ(i, currentZBase);
      } else {
        // Top terrain and top skirt vertices scale dynamically with relief
        posAttr.setZ(i, rawHeights[i] * multiplier);
      }
    }
    posAttr.needsUpdate = true;
    geom.computeVertexNormals();
  }

  private handleKeyDown = (e: KeyboardEvent) => {
    const target = e.target as HTMLElement | null;
    if (target && ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)) return;

    if (['Space', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.code)) {
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
    this.renderer.render(this.scene, this.camera);
  };

  private clearCurrentMesh() {
    if (this.currentMesh) {
      this.scene.remove(this.currentMesh);
      if (this.currentMesh.geometry) this.currentMesh.geometry.dispose();

      if (Array.isArray(this.currentMesh.material)) {
        this.currentMesh.material.forEach((m) => m.dispose());
      } else if (this.currentMesh.material) {
        this.currentMesh.material.dispose();
      }

      this.currentMesh = null;
    }

    if (this.heightmapTexture) {
      this.heightmapTexture.dispose();
      this.heightmapTexture = null;
    }
    if (this.confidenceTexture) {
      this.confidenceTexture.dispose();
      this.confidenceTexture = null;
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

    this.controls.dispose();
    this.renderer.dispose();

    if (this.container && this.renderer.domElement) {
      this.container.removeChild(this.renderer.domElement);
    }
  }
}
