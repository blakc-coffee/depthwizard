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

  constructor(container: HTMLElement) {
    this.container = container;

    // Scene with dark cinematic exhibition backdrop (matches 3D terrain block styling)
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color('#0e1017');

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
    this.controls.maxPolarAngle = Math.PI / 2 - 0.02; // allows inspecting pedestal side walls
    this.controls.target.copy(this.initialTargetPosition);

    // Lights
    this.setupLighting();

    // Resize observer
    this.setupResizeObserver();

    // Start render loop
    this.animate();
  }

  private setupLighting() {
    // Subtle cool ambient fill to preserve deep shadow contrasts in canyons
    const ambientLight = new THREE.AmbientLight(0xdde5ed, 0.32);
    this.scene.add(ambientLight);

    // Warm, dramatic directional sunlight casting distinct shadows across ridges
    const sunLight = new THREE.DirectionalLight(0xfff7e8, 1.8);
    sunLight.position.set(16, 24, 14);
    sunLight.castShadow = true;
    sunLight.shadow.mapSize.width = 2048;
    sunLight.shadow.mapSize.height = 2048;
    sunLight.shadow.bias = -0.0005;
    this.scene.add(sunLight);

    // Subtle cool rim light from opposite side to prevent total blackouts in deep shadow
    const fillLight = new THREE.DirectionalLight(0x7890a8, 0.45);
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
    const zBase = (geom.userData.zBase as number) ?? -0.75;
    if (!rawHeights || !isSkirt) return;

    const posAttr = geom.attributes.position;
    for (let i = 0; i < posAttr.count; i++) {
      const type = isSkirt[i];
      if (type === 2) {
        // Bottom plate or skirt floor stays pinned to zBase
        posAttr.setZ(i, zBase);
      } else {
        // Top terrain & top of skirt scales directly with the multiplier
        posAttr.setZ(i, rawHeights[i] * multiplier);
      }
    }
    posAttr.needsUpdate = true;
    geom.computeVertexNormals();
  }

  public resetView(): void {
    this.camera.position.copy(this.initialCameraPosition);
    this.controls.target.copy(this.initialTargetPosition);
    this.controls.update();
  }

  private animate = () => {
    this.animationFrameId = requestAnimationFrame(this.animate);
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
