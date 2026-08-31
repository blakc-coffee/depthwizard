#!/usr/bin/env python3
"""
Preprocessing script for DepthWizard Phase 2.
Implements patchification, terrain stratification using a height-map heuristic,
reproducible stratified train/val/test splitting, and manifest generation.
"""

import os
import glob
import json
import shutil
import numpy as np
import rasterio
from rasterio.windows import Window

# Not a constraint from Phase 1 — its frozen interface (ml/depth/PHASE1_NOTES.md)
# accepts any input size. 256 is a conventional ML patch size, chosen so it
# divides typical DFC2019 tile dimensions with a small, pad-handled remainder.
DEFAULT_PATCH_SIZE = 256

def classify_terrain(h_array, nodata=None):
    """
    Heuristically classifies a terrain patch based on height-map statistics.
    
    Heuristic rules:
    - sparse (flat / open): standard deviation < 1.0m (flat ground / roads / fields)
    - urban (built-up structures): standard deviation >= 3.5m (large vertical variations from buildings)
    - forested (vegetation / canopy): 1.0m <= standard deviation < 3.5m AND roughness > 0.02
    - hilly (smooth natural terrain): 1.0m <= standard deviation < 3.5m AND roughness <= 0.02
    
    Limitations:
    - This is a heuristic based purely on height-map spatial statistics.
    - It does not utilize semantic land-cover bands or visual imagery.
    - Boundaries between building edges and tree canopies of similar heights may be misclassified.

    NaN handling: some DFC2019 truth tiles carry stray NaN pixels (LiDAR gaps)
    with `nodata` left unset, and `!=` never excludes NaN even when `nodata`
    IS set — so NaN must be excluded explicitly, not just filtered via the
    nodata sentinel. Every NaN-containing patch used to silently default to
    "hilly": np.std()/np.mean() propagate NaN, and every numeric threshold
    comparison against NaN evaluates False, so the patch fell through every
    branch into the final else (found and fixed 2026-08-31 — see
    docs/open_decisions.md; all 33 of DFC2019's original "hilly" patches
    turned out to be this bug, not real hilly terrain).
    """
    valid_mask = ~np.isnan(h_array)
    if nodata is not None:
        valid_mask &= h_array != nodata
    valid_h = h_array[valid_mask]

    if valid_h.size == 0:
        return "sparse", 0.0, 0.0

    std = np.std(valid_h)

    # Calculate surface roughness (mean absolute gradient) — nanmean so a
    # stray NaN pixel only removes the 1-2 gradient cells touching it,
    # instead of poisoning the whole patch's roughness to NaN.
    if h_array.ndim == 2:
        diff_x = np.abs(h_array[:, 1:] - h_array[:, :-1])
        diff_y = np.abs(h_array[1:, :] - h_array[:-1, :])
        roughness = np.nanmean(diff_x) + np.nanmean(diff_y)
    else:
        roughness = 0.0
        
    if std < 1.0:
        terrain = "sparse"
    elif std >= 3.5:
        terrain = "urban"
    else:
        if roughness > 0.02:
            terrain = "forested"
        else:
            terrain = "hilly"
            
    return terrain, float(std), float(roughness)

def patchify_tile(rgb_path, height_path, patch_size, temp_dir, edge_policy="pad"):
    """
    Slices one RGB/height tile pair into patches and returns list of patch metadata.
    Saves patches temporarily to temp_dir before they are assigned to splits.
    """
    os.makedirs(os.path.join(temp_dir, "rgb"), exist_ok=True)
    os.makedirs(os.path.join(temp_dir, "truth"), exist_ok=True)
    
    patches_meta = []
    
    with rasterio.open(rgb_path) as src_rgb, rasterio.open(height_path) as src_truth:
        # Check spatial alignment
        assert src_rgb.width == src_truth.width and src_rgb.height == src_truth.height, "RGB and height tile dimensions must match"
        assert src_rgb.crs == src_truth.crs, "RGB and height tile CRS must match"
        
        width = src_rgb.width
        height = src_rgb.height
        crs = src_rgb.crs
        nodata = src_truth.nodata
        
        x_steps = int(np.ceil(width / patch_size)) if edge_policy == "pad" else width // patch_size
        y_steps = int(np.ceil(height / patch_size)) if edge_policy == "pad" else height // patch_size
        
        base_name = os.path.splitext(os.path.basename(rgb_path))[0].replace("_RGB", "")
        
        for y_idx in range(y_steps):
            for x_idx in range(x_steps):
                col_off = x_idx * patch_size
                row_off = y_idx * patch_size
                
                w_width = min(patch_size, width - col_off)
                w_height = min(patch_size, height - row_off)
                
                window = Window(col_off, row_off, w_width, w_height)
                
                rgb_data = src_rgb.read(window=window)
                truth_data = src_truth.read(window=window)
                
                window_transform = rasterio.windows.transform(window, src_rgb.transform)
                
                padded = False
                if edge_policy == "pad" and (w_width < patch_size or w_height < patch_size):
                    padded = True
                    pad_w = patch_size - w_width
                    pad_h = patch_size - w_height
                    
                    rgb_data = np.pad(rgb_data, ((0, 0), (0, pad_h), (0, pad_w)), mode='constant', constant_values=0)
                    pad_val = nodata if nodata is not None else 0.0
                    truth_data = np.pad(truth_data, ((0, 0), (0, pad_h), (0, pad_w)), mode='constant', constant_values=pad_val)
                
                # Classify terrain using the height map patch
                terrain_type, std, roughness = classify_terrain(truth_data[0], nodata)
                
                patch_id = f"{base_name}_patch_{y_idx}_{x_idx}"
                temp_rgb_path = os.path.join(temp_dir, "rgb", f"{patch_id}_RGB.tif")
                temp_truth_path = os.path.join(temp_dir, "truth", f"{patch_id}_AGL.tif")
                
                # Save RGB patch
                rgb_meta = src_rgb.meta.copy()
                rgb_meta.update({"height": patch_size, "width": patch_size, "transform": window_transform})
                with rasterio.open(temp_rgb_path, "w", **rgb_meta) as dst_rgb:
                    dst_rgb.write(rgb_data)
                    
                # Save Truth patch
                truth_meta = src_truth.meta.copy()
                truth_meta.update({"height": patch_size, "width": patch_size, "transform": window_transform})
                with rasterio.open(temp_truth_path, "w", **truth_meta) as dst_truth:
                    dst_truth.write(truth_data)
                    
                patches_meta.append({
                    "patch_id": patch_id,
                    "source_tile": base_name,
                    "temp_rgb": temp_rgb_path,
                    "temp_truth": temp_truth_path,
                    "terrain_type": terrain_type,
                    "std": std,
                    "roughness": roughness,
                    "padded": padded,
                    "crs": str(crs)
                })
                
    return patches_meta

def patchify_rgb_only(rgb_path, patch_size, temp_dir, edge_policy="pad"):
    """
    Slices an RGB-only tile into patches — no paired ground truth required.
    For Bhuvan/Cartosat Indian-terrain samples (PRD Section 3.2 / 7.0): these
    are for qualitative validation, not training, so no height label exists
    and terrain_type cannot be classified from height statistics.
    """
    os.makedirs(os.path.join(temp_dir, "rgb"), exist_ok=True)
    patches_meta = []

    with rasterio.open(rgb_path) as src_rgb:
        width, height, crs = src_rgb.width, src_rgb.height, src_rgb.crs
        x_steps = int(np.ceil(width / patch_size)) if edge_policy == "pad" else width // patch_size
        y_steps = int(np.ceil(height / patch_size)) if edge_policy == "pad" else height // patch_size
        base_name = os.path.splitext(os.path.basename(rgb_path))[0].replace("_RGB", "")

        for y_idx in range(y_steps):
            for x_idx in range(x_steps):
                col_off, row_off = x_idx * patch_size, y_idx * patch_size
                w_width = min(patch_size, width - col_off)
                w_height = min(patch_size, height - row_off)
                window = Window(col_off, row_off, w_width, w_height)
                rgb_data = src_rgb.read(window=window)
                window_transform = rasterio.windows.transform(window, src_rgb.transform)

                padded = False
                if edge_policy == "pad" and (w_width < patch_size or w_height < patch_size):
                    padded = True
                    rgb_data = np.pad(rgb_data, ((0, 0), (0, patch_size - w_height), (0, patch_size - w_width)),
                                       mode="constant", constant_values=0)

                patch_id = f"{base_name}_patch_{y_idx}_{x_idx}"
                temp_rgb_path = os.path.join(temp_dir, "rgb", f"{patch_id}_RGB.tif")
                rgb_meta = src_rgb.meta.copy()
                rgb_meta.update({"height": patch_size, "width": patch_size, "transform": window_transform})
                with rasterio.open(temp_rgb_path, "w", **rgb_meta) as dst_rgb:
                    dst_rgb.write(rgb_data)

                patches_meta.append({
                    "patch_id": patch_id,
                    "source_tile": base_name,
                    "temp_rgb": temp_rgb_path,
                    "padded": padded,
                    "crs": str(crs)
                })

    return patches_meta

def build_bhuvan_manifest_section(patches, output_dir, source_label, terrain_label="unclassified"):
    """
    Registers Bhuvan/Cartosat validation patches under their own split tag —
    'validation_only', never 'train'/'val'/'test' — so nothing downstream can
    accidentally blend them into the DFC2019/US3D training data. Kept as its
    own manifest section (filter on `source` or `split == "validation_only"`),
    per Phase 2 Chunk 4's frozen contract.
    """
    dest_dir = os.path.join(output_dir, "validation_only", source_label, "rgb")
    os.makedirs(dest_dir, exist_ok=True)

    manifest_entries = []
    for patch in patches:
        rgb_dest = os.path.join(dest_dir, f"{patch['patch_id']}_RGB.tif")
        shutil.move(patch["temp_rgb"], rgb_dest)
        manifest_entries.append({
            "patch_id": patch["patch_id"],
            "source": source_label,
            "source_tile": patch["source_tile"],
            "split": "validation_only",
            "terrain_type": terrain_label,
            "rgb_path": os.path.relpath(rgb_dest, output_dir),
            "truth_path": None,
            "std": None,
            "roughness": None,
            "padded": patch["padded"],
            "crs": patch["crs"],
        })
    return manifest_entries

def split_and_stratify_dataset(patches, output_dir, seed=42, source="dfc2019"):
    """
    Splits patches into train (60%), val (20%), and test (20%) splits,
    stratified by terrain type. Shuffles using fixed seed for reproducibility.
    """
    np.random.seed(seed)
    
    # Group patches by terrain type
    by_terrain = {}
    for p in patches:
        t = p["terrain_type"]
        if t not in by_terrain:
            by_terrain[t] = []
        by_terrain[t].append(p)
        
    split_counts = {"train": 0, "val": 0, "test": 0}
    final_manifest = []
    
    # Process each terrain type group
    for t_type, p_list in by_terrain.items():
        # Shuffle reproducibly
        indices = np.arange(len(p_list))
        np.random.shuffle(indices)
        
        n_total = len(p_list)
        
        # Test split first (20%)
        n_test = max(1 if n_total >= 3 else 0, int(round(0.2 * n_total)))
        # Val split next (20%)
        n_val = max(1 if n_total >= 2 else 0, int(round(0.2 * n_total)))
        # Train gets the rest
        n_train = n_total - n_test - n_val
        
        # Ensure if we only have 1 patch, it goes to train
        if n_total == 1:
            n_train, n_val, n_test = 1, 0, 0
        elif n_total == 2:
            n_train, n_val, n_test = 1, 1, 0
            
        print(f"Terrain '{t_type}': Total={n_total} -> Train={n_train}, Val={n_val}, Test={n_test}")
        
        for idx, list_idx in enumerate(indices):
            patch = p_list[list_idx]
            
            if idx < n_test:
                split = "test"
            elif idx < n_test + n_val:
                split = "val"
            else:
                split = "train"
                
            split_counts[split] += 1
            
            # Destination paths
            dest_rgb_dir = os.path.join(output_dir, split, t_type, "rgb")
            dest_truth_dir = os.path.join(output_dir, split, t_type, "truth")
            os.makedirs(dest_rgb_dir, exist_ok=True)
            os.makedirs(dest_truth_dir, exist_ok=True)
            
            rgb_dest = os.path.join(dest_rgb_dir, f"{patch['patch_id']}_RGB.tif")
            truth_dest = os.path.join(dest_truth_dir, f"{patch['patch_id']}_AGL.tif")
            
            # Move from temp to final split directory
            shutil.move(patch["temp_rgb"], rgb_dest)
            shutil.move(patch["temp_truth"], truth_dest)
            
            # Add to manifest
            final_manifest.append({
                "patch_id": patch["patch_id"],
                "source": source,
                "source_tile": patch["source_tile"],
                "split": split,
                "terrain_type": patch["terrain_type"],
                "rgb_path": os.path.relpath(rgb_dest, output_dir),
                "truth_path": os.path.relpath(truth_dest, output_dir),
                "std": patch["std"],
                "roughness": patch["roughness"],
                "padded": patch["padded"],
                "crs": patch["crs"]
            })
            
    print(f"\nFinal Split Counts: {split_counts}")
    return final_manifest

def main():
    import argparse
    parser = argparse.ArgumentParser(description="DepthWizard Phase 2 Preprocessing Pipeline")
    parser.add_argument("--raw-dir", type=str, default=None,
                        help="Path to the raw DFC2019 dataset folder. If not specified, searches common directories.")
    parser.add_argument("--out-dir", type=str, default="data/processed/v1",
                        help="Path to save versioned processed patches.")
    parser.add_argument("--patch-size", type=int, default=DEFAULT_PATCH_SIZE,
                        help="Target patch size in pixels.")
    parser.add_argument("--bhuvan-dir", type=str, default=None,
                        help="Path to a directory of Bhuvan/Cartosat RGB images (no ground truth) "
                             "for the Indian-terrain validation set. Kept as a separate manifest "
                             "section, never blended into the DFC2019/US3D train/val/test split.")

    args = parser.parse_args()
    
    # Resolve default raw directory
    raw_dir = args.raw_dir
    if raw_dir is None:
        # Check if full dataset path exists
        candidate_paths = [
            "data/raw/dfc2019/track1",
            "data/raw/fixtures/dfc2019_track1"
        ]
        for path in candidate_paths:
            if os.path.exists(path) and glob.glob(os.path.join(path, "rgb", "*.tif")):
                raw_dir = path
                break
        if raw_dir is None:
            raw_dir = "data/raw/fixtures/dfc2019_track1"
            
    processed_dir = args.out_dir
    temp_dir = os.path.join(processed_dir, "temp")
    patch_size = int(args.patch_size)
    
    print("DepthWizard - Phase 2 Dataset Splitting & Stratification")
    print("======================================================")
    print(f"Raw Directory:       {raw_dir}")
    print(f"Processed Directory: {processed_dir}")
    print(f"Patch Size:          {patch_size}x{patch_size}")
    print("======================================================")
    
    # 1. Collect raw tiles
    # sorted() — glob order is filesystem-dependent, not reproducible across
    # reruns/machines; unsorted input order would silently change which
    # patches land in the seeded shuffle's test split
    rgb_files = sorted(glob.glob(os.path.join(raw_dir, "rgb", "*.tif")))
    if not rgb_files:
        print(f"Error: No raw RGB files found in {raw_dir}/rgb")
        return
        
    print(f"Found {len(rgb_files)} raw tiles. Slicing into patches...")
    
    # 2. Patchify all tiles into temp folder
    all_patches = []
    for rgb_path in rgb_files:
        tile_name = os.path.basename(rgb_path).replace("_RGB.tif", "")
        truth_path = os.path.join(raw_dir, "truth", f"{tile_name}_AGL.tif")
        
        if not os.path.exists(truth_path):
            print(f"Warning: No matching height tile found for {rgb_path}. Skipping.")
            continue
            
        print(f"  Processing tile: {tile_name}...")
        patches = patchify_tile(rgb_path, truth_path, patch_size, temp_dir, edge_policy="pad")
        all_patches.extend(patches)
        
    print(f"Generated {len(all_patches)} total patches in temp space.")
    
    # 3. Split and stratify
    manifest_data = split_and_stratify_dataset(all_patches, processed_dir)

    # 4. Bhuvan/Cartosat Indian-terrain validation samples (Chunk 4) — separate
    # from the DFC2019/US3D pipeline, no ground truth required, own manifest section.
    if args.bhuvan_dir:
        bhuvan_files = sorted(glob.glob(os.path.join(args.bhuvan_dir, "*.jpg"))
                               + glob.glob(os.path.join(args.bhuvan_dir, "*.tif")))
        if not bhuvan_files:
            print(f"Warning: --bhuvan-dir given but no images found in {args.bhuvan_dir}")
        for bhuvan_path in bhuvan_files:
            source_label = os.path.splitext(os.path.basename(bhuvan_path))[0]
            print(f"  Processing Bhuvan/Cartosat sample: {source_label}...")
            bhuvan_patches = patchify_rgb_only(bhuvan_path, patch_size, temp_dir)
            manifest_data.extend(
                build_bhuvan_manifest_section(bhuvan_patches, processed_dir, source_label)
            )

    # Write manifest file
    manifest_path = os.path.join(processed_dir, "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest_data, f, indent=2)
    print(f"Saved manifest to: {manifest_path}")
    
    # Clean up temp folder
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
        print("Cleaned up temporary directories.")

if __name__ == "__main__":
    main()

