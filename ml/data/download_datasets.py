#!/usr/bin/env python3
"""
Sourcing and Acquisition Documentation for DepthWizard Datasets.
This script serves as documentation for manual dataset acquisition and outlines
the locations and credentials needed to obtain the source imagery (DFC2019 / US3D).
"""

def acquisition_notes():
    """
    Print sourcing and registration details for DFC2019 (Track 1) and US3D datasets.
    """
    notes = """
================================================================================
                       DEPTHWIZARD - DATASET ACQUISITION
================================================================================

1. DFC2019 / US3D Dataset Sourcing
----------------------------------
- **Sponsor/Host:** IEEE GRSS (Geoscience and Remote Sensing Society) and US3D.
- **Registration Portal:** IEEE GRSS Data Archive (https://www.grss-ieee.org/community/technical-committees/data-fusion/)
  or IEEE DataPort.
- **Manual Acquisition:**
  Because the DFC2019/US3D data requires explicit registration and login credentials,
  programmatic download is not natively supported without user session tokens.
  - Download the raw track files (`Train-Track1-RGB.zip`, `Train-Track1-Truth.zip`, and `Validate-Track1.zip`)
    manually from the portal.
  - Place the downloaded ZIP archives into:
    `./data/raw/archives/DFC2019_track1_trainval/`

2. Directory Layout Contract
----------------------------
The preprocessing pipeline expects the following structure on disk:

tack/
├── data/
│   └── raw/
│       ├── archives/
│       │   └── DFC2019_track1_trainval/
│       │       ├── Train-Track1-RGB.zip
│       │       ├── Train-Track1-Truth.zip
│       │       └── Validate-Track1.zip
│       └── fixtures/
│           └── dfc2019_track1/
│               ├── rgb/
│               │   └── JAX_004_001_RGB.tif (1024x1024 raw tile)
│               └── truth/
│                   └── JAX_004_001_AGL.tif (1024x1024 raw height map)

3. Target Coordinate Systems & Formats
--------------------------------------
- **RGB Imagery:** 3-band, 8-bit GeoTIFF (Red, Green, Blue).
- **Height Map:** 1-band, 32-bit float GeoTIFF representing Above Ground Level (AGL) height.
- **CRS:** UTM projected coordinate systems (e.g., EPSG:32617 for Jacksonville, FL tiles).
- **Units:** Metric (metres).
- **Nodata Value:** -999.0 for height maps.
================================================================================
"""
    print(notes)

if __name__ == "__main__":
    acquisition_notes()
