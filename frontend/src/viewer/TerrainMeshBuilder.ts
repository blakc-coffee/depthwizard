import * as THREE from 'three';

export interface TerrainMeshBuildParams {
  heightmapUrl: string;
  textureUrl: string;
  maxHeight: number;
  isAbsolute: boolean;
  verticalExaggeration?: number;
}

export interface TerrainMeshBuildResult {
  mesh: THREE.Mesh;
  texture: THREE.Texture;
  geometry: THREE.BufferGeometry;
  material: THREE.Material | THREE.Material[];
  width: number;
  height: number;
}

export async function buildTerrainMesh(
  params: TerrainMeshBuildParams
): Promise<TerrainMeshBuildResult> {
  const { heightmapUrl, textureUrl, maxHeight, isAbsolute } = params;
  const exaggeration = params.verticalExaggeration ?? (isAbsolute ? 2.6 : 2.2);

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

  // 3. Grid resolution: 256x256 (65,536 vertices) for high-definition 3D ridges, cliffs, and buildings
  const maxGridDim = 256;
  const gridWidth = Math.min(imgWidth, maxGridDim);
  const gridHeight = Math.min(imgHeight, maxGridDim);

  // Aspect ratio scaling
  const planeWidth = 10;
  const planeHeight = (imgHeight / imgWidth) * planeWidth;

  // Auto-contrast dynamic range stretching
  let minLum = 255;
  let maxLum = 0;
  for (let p = 0; p < data.length; p += 4) {
    if (data[p + 3] >= 64) {
      const lum = data[p];
      if (lum < minLum) minLum = lum;
      if (lum > maxLum) maxLum = lum;
    }
  }
  const lumRange = maxLum > minLum ? maxLum - minLum : 255;

  // Build top surface vertices & UVs
  const topVertexCount = gridWidth * gridHeight;
  const zScale = planeWidth / 10;
  const unitHeightScale = zScale * 1.5;

  const topPositions = new Float32Array(topVertexCount * 3);
  const topUVs = new Float32Array(topVertexCount * 2);
  const rawHeights = new Float32Array(topVertexCount);

  let minRawZ = Infinity;

  for (let iy = 0; iy < gridHeight; iy++) {
    const v = iy / (gridHeight - 1);
    const py = Math.min(imgHeight - 1, Math.floor(v * imgHeight));
    const yPos = planeHeight / 2 - v * planeHeight;

    for (let ix = 0; ix < gridWidth; ix++) {
      const u = ix / (gridWidth - 1);
      const px = Math.min(imgWidth - 1, Math.floor(u * imgWidth));
      const xPos = -planeWidth / 2 + u * planeWidth;

      const idx = iy * gridWidth + ix;
      const pixelIdx = (py * imgWidth + px) * 4;

      const luminance = data[pixelIdx];
      const alpha = data[pixelIdx + 3];

      let norm = (luminance - minLum) / lumRange;
      if (alpha < 64) {
        norm = 0;
      }
      norm = Math.max(0, Math.min(1, norm));

      // Slightly non-linear response to exaggerate canyon drops and cliff ridges
      const shapedHeight = Math.pow(norm, 0.95);
      const unitZ = shapedHeight * unitHeightScale;
      const zValue = unitZ * exaggeration;

      rawHeights[idx] = unitZ;
      if (unitZ < minRawZ) minRawZ = unitZ;

      topPositions[idx * 3] = xPos;
      topPositions[idx * 3 + 1] = yPos;
      topPositions[idx * 3 + 2] = zValue;

      topUVs[idx * 2] = u;
      topUVs[idx * 2 + 1] = 1 - v; // Three.js texture coordinate convention
    }
  }

  // Base pedestal elevation (set below lowest terrain point for solid diorama block)
  const zBase = (minRawZ * exaggeration) - 0.8;

  // Generate top surface triangle indices
  const topIndices: number[] = [];
  for (let iy = 0; iy < gridHeight - 1; iy++) {
    for (let ix = 0; ix < gridWidth - 1; ix++) {
      const a = iy * gridWidth + ix;
      const b = iy * gridWidth + (ix + 1);
      const c = (iy + 1) * gridWidth + (ix + 1);
      const d = (iy + 1) * gridWidth + ix;

      topIndices.push(a, d, b);
      topIndices.push(b, d, c);
    }
  }

  // 4. Build 3D Skirt Walls & Solid Base (Pedestal)
  // Generating separate vertices for skirt walls preserves sharp architectural 90-degree normals
  const skirtPositions: number[] = [];
  const skirtUVs: number[] = [];
  const skirtIndices: number[] = [];
  const skirtRawHeights: number[] = [];
  const skirtIsBottom: number[] = []; // 0: top terrain, 1: skirt top, 2: base floor

  let skirtVertexOffset = topVertexCount;

  function addSkirtQuad(
    top1: [number, number, number],
    top2: [number, number, number],
    bot2: [number, number, number],
    bot1: [number, number, number],
    rawZ1: number,
    rawZ2: number,
    flipWinding: boolean = false
  ) {
    const v0 = skirtVertexOffset;
    skirtPositions.push(...top1, ...top2, ...bot2, ...bot1);
    skirtUVs.push(0, 0, 1, 0, 1, 1, 0, 1);
    skirtRawHeights.push(rawZ1, rawZ2, 0, 0);
    skirtIsBottom.push(1, 1, 2, 2);

    if (flipWinding) {
      skirtIndices.push(v0, v0 + 2, v0 + 1);
      skirtIndices.push(v0, v0 + 3, v0 + 2);
    } else {
      skirtIndices.push(v0, v0 + 1, v0 + 2);
      skirtIndices.push(v0, v0 + 2, v0 + 3);
    }
    skirtVertexOffset += 4;
  }

  // North Edge (iy = 0, y = +planeHeight/2) — facing North (+Y)
  for (let ix = 0; ix < gridWidth - 1; ix++) {
    const i1 = ix;
    const i2 = ix + 1;
    const x1 = topPositions[i1 * 3];
    const y = topPositions[i1 * 3 + 1];
    const z1 = topPositions[i1 * 3 + 2];
    const x2 = topPositions[i2 * 3];
    const z2 = topPositions[i2 * 3 + 2];

    addSkirtQuad(
      [x1, y, z1],
      [x2, y, z2],
      [x2, y, zBase],
      [x1, y, zBase],
      rawHeights[i1],
      rawHeights[i2],
      false
    );
  }

  // South Edge (iy = gridHeight - 1, y = -planeHeight/2) — facing South (-Y)
  const southRowOffset = (gridHeight - 1) * gridWidth;
  for (let ix = 0; ix < gridWidth - 1; ix++) {
    const i1 = southRowOffset + ix;
    const i2 = southRowOffset + (ix + 1);
    const x1 = topPositions[i1 * 3];
    const y = topPositions[i1 * 3 + 1];
    const z1 = topPositions[i1 * 3 + 2];
    const x2 = topPositions[i2 * 3];
    const z2 = topPositions[i2 * 3 + 2];

    addSkirtQuad(
      [x1, y, z1],
      [x2, y, z2],
      [x2, y, zBase],
      [x1, y, zBase],
      rawHeights[i1],
      rawHeights[i2],
      true
    );
  }

  // West Edge (ix = 0, x = -planeWidth/2) — facing West (-X)
  for (let iy = 0; iy < gridHeight - 1; iy++) {
    const i1 = iy * gridWidth;
    const i2 = (iy + 1) * gridWidth;
    const x = topPositions[i1 * 3];
    const y1 = topPositions[i1 * 3 + 1];
    const z1 = topPositions[i1 * 3 + 2];
    const y2 = topPositions[i2 * 3 + 1];
    const z2 = topPositions[i2 * 3 + 2];

    addSkirtQuad(
      [x, y1, z1],
      [x, y2, z2],
      [x, y2, zBase],
      [x, y1, zBase],
      rawHeights[i1],
      rawHeights[i2],
      true
    );
  }

  // East Edge (ix = gridWidth - 1, x = +planeWidth/2) — facing East (+X)
  for (let iy = 0; iy < gridHeight - 1; iy++) {
    const i1 = iy * gridWidth + (gridWidth - 1);
    const i2 = (iy + 1) * gridWidth + (gridWidth - 1);
    const x = topPositions[i1 * 3];
    const y1 = topPositions[i1 * 3 + 1];
    const z1 = topPositions[i1 * 3 + 2];
    const y2 = topPositions[i2 * 3 + 1];
    const z2 = topPositions[i2 * 3 + 2];

    addSkirtQuad(
      [x, y1, z1],
      [x, y2, z2],
      [x, y2, zBase],
      [x, y1, zBase],
      rawHeights[i1],
      rawHeights[i2],
      false
    );
  }

  // Bottom Base Plate (facing -Z)
  const b0 = skirtVertexOffset;
  const hw = planeWidth / 2;
  const hh = planeHeight / 2;
  skirtPositions.push(
    -hw, -hh, zBase,
     hw, -hh, zBase,
     hw,  hh, zBase,
    -hw,  hh, zBase
  );
  skirtUVs.push(0, 0, 1, 0, 1, 1, 0, 1);
  skirtRawHeights.push(0, 0, 0, 0);
  skirtIsBottom.push(2, 2, 2, 2);

  skirtIndices.push(b0, b0 + 3, b0 + 2);
  skirtIndices.push(b0, b0 + 2, b0 + 1);

  // Combine arrays into a single BufferGeometry
  const totalVertices = topVertexCount + skirtPositions.length / 3;
  const allPositions = new Float32Array(totalVertices * 3);
  allPositions.set(topPositions, 0);
  allPositions.set(skirtPositions, topVertexCount * 3);

  const allUVs = new Float32Array(totalVertices * 2);
  allUVs.set(topUVs, 0);
  allUVs.set(skirtUVs, topVertexCount * 2);

  const allRawHeights = new Float32Array(totalVertices);
  allRawHeights.set(rawHeights, 0);
  allRawHeights.set(skirtRawHeights, topVertexCount);

  const allIsSkirt = new Uint8Array(totalVertices);
  allIsSkirt.set(new Uint8Array(topVertexCount).fill(0), 0);
  allIsSkirt.set(skirtIsBottom, topVertexCount);

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(allPositions, 3));
  geometry.setAttribute('uv', new THREE.BufferAttribute(allUVs, 2));

  // Combine indices with Material Groups: Group 0 = Top Surface, Group 1 = Skirt Walls & Base Floor
  const topIndexCount = topIndices.length;
  const skirtIndexCount = skirtIndices.length;
  const allIndices = new Uint32Array(topIndexCount + skirtIndexCount);
  allIndices.set(topIndices, 0);
  allIndices.set(skirtIndices, topIndexCount);

  geometry.setIndex(new THREE.BufferAttribute(allIndices, 1));
  geometry.addGroup(0, topIndexCount, 0); // Material 0: Satellite Texture
  geometry.addGroup(topIndexCount, skirtIndexCount, 1); // Material 1: Dark Pedestal Base

  geometry.computeVertexNormals();

  // Store metadata for real-time slider updates
  geometry.userData = {
    rawHeights: allRawHeights,
    isSkirt: allIsSkirt,
    minRawZ,
    zBase,
    baseMultiplier: exaggeration,
    maxHeight: maxHeight || 255.0,
  };

  // 5. Load RGB surface texture
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
        tex.anisotropy = 8;
        resolve(tex);
      },
      undefined,
      (err) => reject(err)
    );
  });

  // Top terrain material: realistic matte satellite texture with DoubleSide rendering
  const terrainMaterial = new THREE.MeshStandardMaterial({
    map: texture,
    roughness: 0.8,
    metalness: 0.05,
    flatShading: false,
    side: THREE.DoubleSide,
  });

  // Skirt & Pedestal base material: architectural dark graphite slate with DoubleSide rendering
  const baseMaterial = new THREE.MeshStandardMaterial({
    color: new THREE.Color('#383b48'),
    roughness: 0.85,
    metalness: 0.1,
    flatShading: false,
    side: THREE.DoubleSide,
  });

  const materials = [terrainMaterial, baseMaterial];
  const mesh = new THREE.Mesh(geometry, materials);

  // Rotate plane so Z points upwards in 3D scene (X-Z floor, Y height)
  mesh.rotation.x = -Math.PI / 2;
  mesh.receiveShadow = true;
  mesh.castShadow = true;

  return {
    mesh,
    texture,
    geometry,
    material: materials,
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
