/**
 * Procedural 3D Terrain & Satellite Texture Generator for DepthWizard.
 * Produces authentic, high-relief DEM heightmaps and satellite textures
 * for Before Disaster, After Disaster, and Difference Map modes.
 */

export interface SampleTerrainDataset {
  heightmapUrl: string;
  textureUrl: string;
  width: number;
  height: number;
  rawHeights: Float32Array;
}

const cache = new Map<string, SampleTerrainDataset>();

export function getSampleTerrain(mode: 'before' | 'after' | 'difference' = 'before'): SampleTerrainDataset {
  const cached = cache.get(mode);
  if (cached) return cached;

  const width = 128;
  const height = 128;
  const rawHeights = new Float32Array(width * height);

  // 1. Generate procedural elevations
  for (let iy = 0; iy < height; iy++) {
    const ny = (iy / (height - 1)) * 2 - 1; // [-1, 1]
    for (let ix = 0; ix < width; ix++) {
      const nx = (ix / (width - 1)) * 2 - 1; // [-1, 1]
      const idx = iy * width + ix;

      // Base mountain massif
      const distFromCenter = Math.hypot(nx, ny);
      let h = Math.exp(-distFromCenter * distFromCenter * 2.5) * 1.5;

      // Mountain ridge spines
      const ridge1 = Math.exp(-Math.pow(nx * 1.6 - Math.sin(ny * 2.2) * 0.35, 2) * 4.5) * (0.6 + 0.4 * Math.cos(ny * 1.8));
      const ridge2 = Math.exp(-Math.pow((nx - 0.25) * 2.0 + ny * 1.2, 2) * 3.8) * 0.55;
      h += ridge1 + ridge2;

      // High-frequency crags & erosion gullies
      h += 0.18 * Math.sin(nx * 7.5 + ny * 5.0) * Math.cos(ny * 8.0 - nx * 3.5);
      h += 0.08 * Math.sin(nx * 15.0 - ny * 12.0);
      h += 0.04 * Math.cos(nx * 28.0 + ny * 20.0);

      // Meandering river canyon carving across the valley
      const canyonPath = Math.abs(nx + Math.sin(ny * 3.0) * 0.35 + 0.2);
      if (canyonPath < 0.28) {
        const canyonDepth = (1 - canyonPath / 0.28) * 0.45;
        h = Math.max(0.02, h - canyonDepth);
      }

      // Mode-specific topographic deformation
      if (mode === 'after') {
        // Massive structural landslide / collapse on southeastern slope
        const dx = nx - 0.35;
        const dy = ny - 0.2;
        const scarDist = Math.hypot(dx * 2.2, dy * 1.3);
        if (scarDist < 0.45) {
          const collapse = (1 - scarDist / 0.45) * 0.75;
          h = Math.max(0.05, h - collapse);
        }

        // Debris fan accumulation in the lower canyon
        const ddx = nx - 0.55;
        const ddy = ny - 0.45;
        const debrisDist = Math.hypot(ddx * 1.8, ddy * 1.8);
        if (debrisDist < 0.35) {
          h += (1 - debrisDist / 0.35) * 0.38;
        }
      } else if (mode === 'difference') {
        // Delta mode: volumetric elevation displacement
        const dx = nx - 0.35;
        const dy = ny - 0.2;
        const scarDist = Math.hypot(dx * 2.2, dy * 1.3);
        if (scarDist < 0.45) {
          h = (1 - scarDist / 0.45) * 0.8;
        } else {
          h = Math.max(0.04, h * 0.35);
        }
      }

      // Clean rectangular skirt boundary falloff
      const edgeFalloffX = Math.max(0, 1 - Math.pow(Math.abs(nx), 8));
      const edgeFalloffY = Math.max(0, 1 - Math.pow(Math.abs(ny), 8));
      h = h * edgeFalloffX * edgeFalloffY;

      rawHeights[idx] = Math.max(0, h);
    }
  }

  // Find min and max for normalization
  let minH = Infinity;
  let maxH = -Infinity;
  for (let i = 0; i < rawHeights.length; i++) {
    if (rawHeights[i] < minH) minH = rawHeights[i];
    if (rawHeights[i] > maxH) maxH = rawHeights[i];
  }
  const hRange = maxH - minH || 1;

  if (typeof document === 'undefined') {
    return {
      heightmapUrl: '',
      textureUrl: '',
      width,
      height,
      rawHeights,
    };
  }

  // 2. Render 8-bit grayscale Heightmap Canvas
  const hCanvas = document.createElement('canvas');
  hCanvas.width = width;
  hCanvas.height = height;
  const hCtx = hCanvas.getContext('2d')!;
  const hImgData = hCtx.createImageData(width, height);

  for (let i = 0; i < rawHeights.length; i++) {
    const val = Math.round(((rawHeights[i] - minH) / hRange) * 255);
    const p = i * 4;
    hImgData.data[p] = val;
    hImgData.data[p + 1] = val;
    hImgData.data[p + 2] = val;
    hImgData.data[p + 3] = 255;
  }
  hCtx.putImageData(hImgData, 0, 0);

  // 3. Render High-Resolution Realistic Satellite Texture Canvas
  const tCanvas = document.createElement('canvas');
  tCanvas.width = 256;
  tCanvas.height = 256;
  const tCtx = tCanvas.getContext('2d')!;
  const tImgData = tCtx.createImageData(256, 256);

  for (let py = 0; py < 256; py++) {
    const iy = Math.min(height - 1, Math.floor((py / 255) * height));
    const ny = (py / 255) * 2 - 1;

    for (let px = 0; px < 256; px++) {
      const ix = Math.min(width - 1, Math.floor((px / 255) * width));
      const nx = (px / 255) * 2 - 1;
      const idx = iy * width + ix;
      const normH = (rawHeights[idx] - minH) / hRange;
      const tIdx = (py * 256 + px) * 4;

      let r = 0;
      let g = 0;
      let b = 0;

      if (mode === 'difference') {
        // Difference Mode: Thermal/chromatic satellite delta map
        const dx = nx - 0.35;
        const dy = ny - 0.2;
        const scarDist = Math.hypot(dx * 2.2, dy * 1.3);

        const ddx = nx - 0.55;
        const ddy = ny - 0.45;
        const debrisDist = Math.hypot(ddx * 1.8, ddy * 1.8);

        if (scarDist < 0.45) {
          // Intense Crimson / Red for Structural Collapse Zone
          const intensity = 1 - scarDist / 0.45;
          r = Math.round(220 + 35 * intensity);
          g = Math.round(30 + 40 * (1 - intensity));
          b = Math.round(30 + 50 * (1 - intensity));
        } else if (debrisDist < 0.35) {
          // Electric Cyan / Teal for Deposition & Flooding
          const intensity = 1 - debrisDist / 0.35;
          r = Math.round(6 + 40 * (1 - intensity));
          g = Math.round(182 + 50 * intensity);
          b = Math.round(212 + 40 * intensity);
        } else {
          // Subtle dark slate for stable unchanged zones
          const v = Math.round(35 + normH * 45);
          r = v;
          g = v + 8;
          b = v + 18;
        }
      } else if (mode === 'after') {
        // After Disaster: Mudslide scar, rubble deposits, and weathered rock
        const dx = nx - 0.35;
        const dy = ny - 0.2;
        const scarDist = Math.hypot(dx * 2.2, dy * 1.3);

        const ddx = nx - 0.55;
        const ddy = ny - 0.45;
        const debrisDist = Math.hypot(ddx * 1.8, ddy * 1.8);

        if (scarDist < 0.45) {
          // Raw exposed landslide earth & mud
          r = 115;
          g = 78;
          b = 52;
        } else if (debrisDist < 0.35) {
          // Sediment debris fan
          r = 140;
          g = 105;
          b = 75;
        } else {
          // Surrounding landscape
          if (normH > 0.72) {
            // Snow peak
            r = 235; g = 240; b = 245;
          } else if (normH > 0.45) {
            // Exposed granite & scree
            r = 110; g = 115; b = 120;
          } else if (normH > 0.18) {
            // Conifer forest
            r = 45; g = 75; b = 38;
          } else {
            // River valley
            r = 50; g = 85; b = 110;
          }
        }
      } else {
        // Before Disaster: Pristine satellite orthophoto
        if (normH > 0.72) {
          // Snow-capped alpine peaks
          const snowShade = Math.round(230 + normH * 25);
          r = snowShade - 5;
          g = snowShade;
          b = snowShade + 5;
        } else if (normH > 0.42) {
          // Rocky ridges and subalpine scree
          const rock = Math.round(95 + (normH - 0.42) * 70);
          r = rock;
          g = rock + 5;
          b = rock + 10;
        } else if (normH > 0.15) {
          // Dense evergreen pine forest
          const forest = Math.round(35 + (normH - 0.15) * 45);
          r = forest;
          g = forest + 35;
          b = forest + 10;
        } else {
          // River channel and meadow valley floor
          const canyonPath = Math.abs(nx + Math.sin(ny * 3.0) * 0.35 + 0.2);
          if (canyonPath < 0.12) {
            // Clear river water
            r = 14;
            g = 116;
            b = 168;
          } else {
            // Riverbank meadow
            r = 75;
            g = 110;
            b = 55;
          }
        }
      }

      tImgData.data[tIdx] = r;
      tImgData.data[tIdx + 1] = g;
      tImgData.data[tIdx + 2] = b;
      tImgData.data[tIdx + 3] = 255;
    }
  }
  tCtx.putImageData(tImgData, 0, 0);

  const dataset: SampleTerrainDataset = {
    heightmapUrl: hCanvas.toDataURL('image/png'),
    textureUrl: tCanvas.toDataURL('image/png'),
    width,
    height,
    rawHeights,
  };

  cache.set(mode, dataset);
  return dataset;
}
