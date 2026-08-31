import * as THREE from 'three';

export interface TerrainMeshBuildParams {
  heightmapUrl: string;
  textureUrl: string;
  maxHeight: number;
  isAbsolute: boolean;
}

export interface TerrainMeshBuildResult {
  mesh: THREE.Mesh;
  texture: THREE.Texture;
  geometry: THREE.BufferGeometry;
  material: THREE.Material;
  width: number;
  height: number;
}

export async function buildTerrainMesh(
  params: TerrainMeshBuildParams
): Promise<TerrainMeshBuildResult> {
  const { heightmapUrl, textureUrl, maxHeight } = params;

  // 1. Load heightmap image in browser HTMLImageElement
  const heightmapImg = await loadImage(heightmapUrl);
  const imgWidth = heightmapImg.width || 256;
  const imgHeight = heightmapImg.height || 256;

  // 2. Decode pixel data using offscreen Canvas ImageData
  const canvas = document.createElement('canvas');
  canvas.width = imgWidth;
  canvas.height = imgHeight;
  const ctx = canvas.getContext('2d');

  if (!ctx) {
    throw new Error('Failed to create offscreen 2D canvas context for heightmap decoding.');
  }

  ctx.drawImage(heightmapImg, 0, 0);
  const imageData = ctx.getImageData(0, 0, imgWidth, imgHeight);
  const data = imageData.data; // RGBA buffer

  // 3. Subsample grid resolution to max 128x128 vertices for fast, lightweight rendering
  const maxGridDim = 128;
  const gridWidth = Math.min(imgWidth, maxGridDim);
  const gridHeight = Math.min(imgHeight, maxGridDim);

  // Aspect ratio scaling
  const planeWidth = 10;
  const planeHeight = (imgHeight / imgWidth) * planeWidth;

  const geometry = new THREE.PlaneGeometry(
    planeWidth,
    planeHeight,
    gridWidth - 1,
    gridHeight - 1
  );

  const posAttr = geometry.attributes.position;
  const vertexCount = posAttr.count;

  // Scale Z displacement visually
  const zScale = planeWidth / 10;
  const maxMetersNorm = maxHeight > 0 ? maxHeight : 255.0;

  for (let i = 0; i < vertexCount; i++) {
    const u = (i % gridWidth) / (gridWidth - 1);
    const v = Math.floor(i / gridWidth) / (gridHeight - 1);

    const px = Math.min(imgWidth - 1, Math.floor(u * imgWidth));
    const py = Math.min(imgHeight - 1, Math.floor((1 - v) * imgHeight));

    const pixelIdx = (py * imgWidth + px) * 4;

    const luminance = data[pixelIdx]; // Channel 0 (L)
    const alpha = data[pixelIdx + 3]; // Channel 1 (A validity mask)

    let normalizedHeight = luminance / 255.0;

    // Handle NoData: if alpha mask is zero, zero out vertex height
    if (alpha < 128) {
      normalizedHeight = 0;
    }

    // Displacement magnitude
    const displacement = (normalizedHeight * maxMetersNorm) / maxMetersNorm;
    const zValue = displacement * (zScale * 1.8);

    posAttr.setZ(i, zValue);
  }

  geometry.computeVertexNormals();

  // 4. Load RGB surface texture
  const textureLoader = new THREE.TextureLoader();
  if (textureUrl.startsWith('http')) {
    textureLoader.setCrossOrigin('anonymous');
  }

  const texture = await new Promise<THREE.Texture>((resolve, reject) => {
    textureLoader.load(
      textureUrl,
      (tex) => {
        tex.colorSpace = THREE.SRGBColorSpace;
        tex.wrapS = THREE.ClampToEdgeWrapping;
        tex.wrapT = THREE.ClampToEdgeWrapping;
        resolve(tex);
      },
      undefined,
      (err) => reject(err)
    );
  });

  const material = new THREE.MeshStandardMaterial({
    map: texture,
    roughness: 0.65,
    metalness: 0.1,
    side: THREE.DoubleSide,
  });

  const mesh = new THREE.Mesh(geometry, material);

  // Rotate plane so Z points upwards in 3D scene (X-Z floor, Y height)
  mesh.rotation.x = -Math.PI / 2;
  mesh.receiveShadow = true;
  mesh.castShadow = true;

  return {
    mesh,
    texture,
    geometry,
    material,
    width: imgWidth,
    height: imgHeight,
  };
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    if (src.startsWith('http')) {
      img.crossOrigin = 'anonymous';
    }
    img.onload = () => resolve(img);
    img.onerror = (e) => reject(e);
    img.src = src;
  });
}
