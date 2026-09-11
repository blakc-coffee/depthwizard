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

  // 3D Reconnaissance Flythrough state
  private isFlying: boolean = false;
  private flightProgress: number = 0;
  private flightClock: THREE.Clock = new THREE.Clock();
  private flightCurve: THREE.CatmullRomCurve3 | null = null;
  private flightSpeed: number = 0.045; // ~22s per complete reconnaissance loop
  private lookAheadOffset: number = 0.05;
  private currentLookTarget: THREE.Vector3 = new THREE.Vector3(0, 0, 0);

  public onFlightStateChange?: (isFlying: boolean) => void;

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

    // Stop flythrough on direct user interaction with canvas
    this.renderer.domElement.addEventListener('pointerdown', this.handleUserInteraction);
    this.renderer.domElement.addEventListener('wheel', this.handleUserInteraction, { passive: true });

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

    // Build 3D reconnaissance flight curve fitted to terrain dimensions
    this.buildFlightPath(buildResult.width, buildResult.height);

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

  private buildFlightPath(imgWidth: number, imgHeight: number): void {
    const hw = 5.0; // half-width of 10-unit mesh
    const hh = ((imgHeight || 256) / (imgWidth || 256)) * hw; // half-depth

    // Strategic reconnaissance waypoints hovering over and through the terrain:
    // 0. South high approach: overview of entire terrain block
    // 1. South-West banking descent: sweeps toward side cliffs
    // 2. Center low-altitude skimming pass: clears building roofs and peaks at close range
    // 3. East flank low sweep: close inspection of structures
    // 4. East cliff banking climb: ascending turn showcasing pedestal side walls
    // 5. North high overlook: panoramic view from opposite angle
    // 6. West descending ridge turn: completing the reconnaissance loop
    const waypoints = [
      new THREE.Vector3(0, 5.8, hh * 1.35),
      new THREE.Vector3(-hw * 0.75, 3.2, hh * 0.6),
      new THREE.Vector3(-hw * 0.25, 2.0, 0.1),
      new THREE.Vector3(hw * 0.65, 2.5, -hh * 0.4),
      new THREE.Vector3(hw * 0.9, 4.2, 0),
      new THREE.Vector3(hw * 0.2, 5.5, -hh * 1.25),
      new THREE.Vector3(-hw * 0.85, 4.0, -hh * 0.3),
    ];

    this.flightCurve = new THREE.CatmullRomCurve3(waypoints, true, 'centripetal');
    this.flightProgress = 0;
  }

  private handleUserInteraction = () => {
    if (this.isFlying) {
      this.stopFlythrough();
    }
  };

  public startFlythrough(): void {
    if (!this.flightCurve) {
      this.buildFlightPath(256, 256);
    }
    this.isFlying = true;
    this.controls.enabled = false;
    this.flightClock.start();
    this.onFlightStateChange?.(true);
  }

  public stopFlythrough(): void {
    if (!this.isFlying) return;
    this.isFlying = false;
    this.controls.enabled = true;
    this.controls.target.copy(this.currentLookTarget);
    this.controls.update();
    this.onFlightStateChange?.(false);
  }

  public toggleFlythrough(): boolean {
    if (this.isFlying) {
      this.stopFlythrough();
      return false;
    } else {
      this.startFlythrough();
      return true;
    }
  }

  public getIsFlying(): boolean {
    return this.isFlying;
  }

  public resetView(): void {
    this.stopFlythrough();
    this.camera.position.copy(this.initialCameraPosition);
    this.controls.target.copy(this.initialTargetPosition);
    this.controls.update();
  }

  private animate = () => {
    this.animationFrameId = requestAnimationFrame(this.animate);

    if (this.isFlying && this.flightCurve) {
      const delta = Math.min(this.flightClock.getDelta(), 0.1);
      this.flightProgress = (this.flightProgress + delta * this.flightSpeed) % 1.0;

      // Position along 3D reconnaissance flight path
      const camPos = this.flightCurve.getPointAt(this.flightProgress);
      this.camera.position.copy(camPos);

      // Look-ahead target along flight path
      const lookProgress = (this.flightProgress + this.lookAheadOffset) % 1.0;
      const forwardPoint = this.flightCurve.getPointAt(lookProgress);

      // Blend forward trajectory with terrain center (0, 0.35, 0) for natural UAV tilt
      const targetLook = new THREE.Vector3()
        .copy(forwardPoint)
        .multiplyScalar(0.7)
        .add(new THREE.Vector3(0, 0.35, 0).multiplyScalar(0.3));

      this.currentLookTarget.lerp(targetLook, 0.1);
      this.camera.lookAt(this.currentLookTarget);

      this.controls.target.copy(this.currentLookTarget);
    } else {
      this.controls.update();
    }

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
    this.stopFlythrough();

    if (this.animationFrameId !== null) {
      cancelAnimationFrame(this.animationFrameId);
    }

    if (this.resizeObserver) {
      this.resizeObserver.disconnect();
    }

    if (this.renderer && this.renderer.domElement) {
      this.renderer.domElement.removeEventListener('pointerdown', this.handleUserInteraction);
      this.renderer.domElement.removeEventListener('wheel', this.handleUserInteraction);
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
