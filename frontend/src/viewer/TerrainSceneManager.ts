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

  private initialCameraPosition = new THREE.Vector3(0, 8, 12);
  private initialTargetPosition = new THREE.Vector3(0, 0, 0);

  constructor(container: HTMLElement) {
    this.container = container;

    // Scene
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color('#F6F4EC');

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
    this.controls.maxPolarAngle = Math.PI / 2 - 0.05;
    this.controls.target.copy(this.initialTargetPosition);

    // Lights
    this.setupLighting();

    // Resize observer
    this.setupResizeObserver();

    // Start render loop
    this.animate();
  }

  private setupLighting() {
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.75);
    this.scene.add(ambientLight);

    const sunLight = new THREE.DirectionalLight(0xffffff, 1.2);
    sunLight.position.set(10, 20, 15);
    sunLight.castShadow = true;
    sunLight.shadow.mapSize.width = 1024;
    sunLight.shadow.mapSize.height = 1024;
    this.scene.add(sunLight);

    const fillLight = new THREE.DirectionalLight(0xece9dd, 0.4);
    fillLight.position.set(-10, 10, -10);
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
    const material = this.currentMesh.material as THREE.MeshStandardMaterial;

    if (mode === '3d') {
      if (this.currentTexture) material.map = this.currentTexture;
      this.currentMesh.rotation.x = -Math.PI / 2;
    } else if (mode === '2d_heightmap') {
      if (this.heightmapTexture) material.map = this.heightmapTexture;
      this.currentMesh.rotation.x = -Math.PI / 2;
    } else if (mode === 'confidence') {
      if (this.confidenceTexture) {
        material.map = this.confidenceTexture;
      } else if (this.currentTexture) {
        material.map = this.currentTexture;
      }
      this.currentMesh.rotation.x = -Math.PI / 2;
    }

    material.needsUpdate = true;
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
