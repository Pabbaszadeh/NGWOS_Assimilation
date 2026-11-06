# Assimilating USGS NGWOS Streamflow Observations into WRF-Hydro

Configuration files, model domains and scripts for the data assimilation experiments in:

> Shirkhanloo, F., RafieeiNasab, A., Stonewall, A., Wherry, S., Simeone, C. E., and Abbaszadeh, P. *Exploring the Benefits of Assimilating the USGS NGWOS Streamflow Observations into a Distributed Hydrology Model.* *Advances in Water Resources*. DOI will be added on publication.

## Overview

The study assimilates hourly streamflow from four new USGS Next Generation Water Observing System (NGWOS) gages into WRF-Hydro, the core of the National Water Model, in four Cascade headwater subbasins of the Willamette River Basin, Oregon. Assimilation uses HydroDART, the WRF-Hydro interface of the Data Assimilation Research Testbed (DART), with a 50-member ensemble adjustment Kalman filter (EAKF).

The ensembles run WRF-Hydro in channel-only mode (`forc_typ = 9`). The channel network is driven by two inflows read from the CHRTOUT files of a calibrated, full-configuration reference run: `qSfcLatRunoff` (lateral surface runoff) and `qBucket` (groundwater-bucket discharge). At every cycle the filter updates channel streamflow (`qlink1`) together with two correction multipliers for these inflows:

| Multiplier | Scales | Bounds |
| --- | --- | --- |
| `qBucketMult` (θ1) | `qBucket` | 0.1–10 |
| `qSfcLatRunoffMult` (θ2) | `qSfcLatRunoff` | 0.1–10 |

WRF-Hydro cannot read these multipliers, so the scripts in this repository feed them back: before each model advance, they are applied to the channel forcing that the model does read.

## Study subbasins

| Subbasin | Folder | NGWOS gage (assimilated) | Calibration gage | Cycle | Localization cutoff (rad) | Posterior inflation |
| --- | --- | --- | --- | --- | --- | --- |
| South Fork McKenzie River | `Mckenzie_River` | 14159130 | 14159200 | 24 h | 6.278e-4 | none |
| Breitenbush River | `Breitenbush_River` | 14178610 | 14179000 | 24 h | 4.709e-4 | none |
| South Santiam River | `South_Santiam_River` | 14184300 | 14185000 | 1 h | 7.063e-4 | RTPS, α = 0.8 |
| Quartzville Creek | `Quartzville_Creek` | 14185865 | 14185900 | 1 h | 3.924e-4 | RTPS, α = 0.8 |

The experiments cover November 2023 to September 2024. October 2023 was a one-month warm start, and the files in each `RESTART/` folder hold the model state at 2023-11-01 00:00. The Breitenbush gage record begins in late May 2024, so that subbasin has a shorter assimilation period.

Settings shared by all subbasins (see each `input.nml` and yaml):

- 50 ensemble members. The initial spread comes from lognormal perturbations (log-space standard deviation 0.2) of the initial state and the two multipliers.
- Observation error: 17% of the observed flow (`obs_fraction_for_error = 0.17`).
- Forcing noise at every advance: zero-mean Gaussian, standard deviation 40% of the flux, truncated at 0.
- Adaptive prior inflation (`inf_flavor = 2`): initial value 1.0, standard deviation 0.6, bounds 1–10, damping 0.9.
- Gaspari–Cohn localization. The cutoff is half of the subbasin's `max_link_distance`, converted to radians.

## Repository structure

```
.
├── scripts/                         Python scripts shared by all subbasins
│   ├── ens_setup_NWM_channel-only.py
│   ├── uniform_theta.py
│   ├── perturb_channel_only_forcing_v4.py
│   ├── noise_qBucket_relative.py
│   └── noise_qSfcLatRunoff_relative.py
├── Mckenzie_River/                  one folder per subbasin, all with this layout
│   ├── Mckenzie_River.yaml          experiment configuration (hydrodartpy / wrfhydropy)
│   ├── input.nml                    DART namelist
│   ├── wanted_gages_list.txt        NGWOS gage that is assimilated
│   ├── list_of_obs_files.txt        hourly USGS time-slice files given to the observation converter
│   ├── DOMAIN/                      WRF-Hydro domain, parameter and namelist files
│   └── RESTART/                     initial model state (HYDRO_RST and RESTART)
├── Breitenbush_River/
├── Quartzville_Creek/
└── South_Santiam_River/
```

`DOMAIN/` contains the WRF-Hydro domain and parameter files (`Fulldom.nc`, `geo_em.d0x.nc`, `Route_Link.nc`, `GWBUCKPARM.nc`, `HYDRO_TBL_2D.nc`, `soil_properties.nc`, `spatialweights.nc`, `wrfinput_d0x.nc`, `GEOGRID_LDASOUT_Spatial_Metadata.nc`), the model namelists (`hydro.namelist`, `namelist.hrldas`) and the wrfhydropy patch files (`hydro_namelist_patches.json`, `hrldas_namelist_patches.json`, `compile_options.json`). The domains are subsets of the CONUS domain of the USGS Integrated Water Availability Assessment (IWAA) WRF-Hydro application. Each netCDF file's `history` attribute records how it was cut. In each `Route_Link.nc`, the NGWOS gage is assigned to its channel reach (`gages`) and the upstream–downstream connectivity (`link`, `to`) is rebuilt for the subset network.

Some file names contain `:` (WRF-Hydro's restart naming), so clone the repository on Linux or macOS.

## Scripts

`perturb_channel_only_forcing_v4.py`, `noise_qBucket_relative.py` and `noise_qSfcLatRunoff_relative.py` are modified versions of the forcing-perturbation scripts in DART (`models/wrf_hydro/python/perturb/`), which is distributed under the Apache License 2.0. The main changes are the multiplier feedback (`--use_theta`, including the reordering from `Route_Link` to `feature_id` order).

**`ens_setup_NWM_channel-only.py`** is the ensemble constructor named in each yaml (`ensemble: constructor`). wrfhydropy runs it when it builds the ensemble. It switches every member to channel-only mode: forcing type 9, forcing read from `FORCING_perturbed`, nudging options cleared, compound channel on, hourly restarts and output, and channel-bucket influx output off. All members get the same settings.

**`uniform_theta.py`** makes the multipliers spatially uniform. It reads the member's latest `parameter_restart.<date>.nc` (written by DART) and replaces each multiplier field with its mean over the valid channel links, kept within DART's clamp bounds. Each member then carries one value per multiplier. Without `--apply` it only prints a report. With `--ens_dir` it can also compare the spread across members before and after averaging, and `--preserve_spread` rescales that spread. In the experiments it runs once per member (`--run_dir . --apply`).

**`perturb_channel_only_forcing_v4.py`** builds the forcing for the next model advance. It reads the cycle start and length from the member's `namelist.hrldas`, and for each hourly CHRTOUT file in the cycle it:

1. multiplies the original `qBucket` and `qSfcLatRunoff` by the member's multipliers (`--use_theta`). DART stores parameters in `Route_Link` order and the CHRTOUT files are in `feature_id` order, so the multipliers are reordered first (`--route_link`). The multipliers are always applied to the original forcing, so they do not compound from one cycle to the next;
2. adds noise from the two noise models;
3. writes the result to `FORCING_perturbed/` and points `namelist.hrldas` to that folder.

**`noise_qBucket_relative.py`** and **`noise_qSfcLatRunoff_relative.py`** are the noise models for the two inflows: `x* = max(0, x + ε)`, `ε ~ N(0, (0.4x)²)` (Eq. 1 in the paper). Each defines `noise_model(x, seed)` and offsets the seed differently, so the two inflows get independent noise.

## One assimilation cycle

At each cycle (24 h or 1 h), hydrodartpy's `run_filter_experiment.py`:

1. runs DART `filter`, which assimilates the NGWOS observations in the window and writes the updated `qlink1` and multipliers to each member's restart and parameter files;
2. runs the yaml's `noise_cmd` in every member folder: `uniform_theta.py` and then `perturb_channel_only_forcing_v4.py` (Eq. 3 in the paper);
3. advances every member with WRF-Hydro in channel-only mode to the next cycle.

## Requirements

- [WRF-Hydro](https://github.com/NCAR/wrf_hydro_nwm_public), tag [`applications/IWAA_Retrospective`](https://github.com/NCAR/wrf_hydro_nwm_public/releases/tag/applications%2FIWAA_Retrospective), compiled with gfortran (`model_config: nwm`)
- [DART](https://github.com/NCAR/DART) v11.20.0 ([doi:10.5065/D6WQ0202](https://doi.org/10.5065/D6WQ0202)), including the HydroDART Python package `hydrodartpy` in `models/wrf_hydro/hydro_dart_py`
- [wrfhydropy](https://github.com/NCAR/wrf_hydro_py)
- Python 3 with numpy, xarray, netCDF4 and f90nml
- MPI. The job settings in the yamls use Slurm (`srun`).

Model calibration was done separately with PyWrfHydroCalib and is not part of this repository.

## Data not included

- **Channel forcing.** Hourly CHRTOUT files with `qSfcLatRunoff` and `qBucket` from the reference full-configuration WRF-Hydro run, read from the yaml's `perturb_forcing: src_dir`. The reference run was forced with bias-adjusted CONUS404 ([doi:10.5066/P9JE61P7](https://doi.org/10.5066/P9JE61P7)). Model outputs are available from the authors on request.
- **NGWOS observations.** Hourly discharge from [USGS Water Data for the Nation](https://waterdata.usgs.gov/), retrieved with the dataRetrieval R package and written as WRF-Hydro nudging time-slice files (`*.60min.usgsTimeSlice.ncdf`).
- **DART observation sequence files.** Made once, before the experiments, from the time-slice files with DART's USGS streamflow converter. The yamls therefore set `prepare: False`, so these files must already exist in `all_obs_dir`.

## Running an experiment

1. **Paths.** The yaml, json, namelist and text files keep the absolute paths of the original runs on Portland State University's Coeus cluster (`/scratch/fatemehs-fatemehs/...`, `/home/fatemehs/...`). Point them to your own DART and WRF-Hydro builds, data and output folders. To list every path that needs changing:

   ```bash
   grep -rnE '/scratch/|/home/' --include='*.yaml' --include='*.json' --include='*.nml' --include='*.txt' .
   ```

2. **Install hydrodartpy:**

   ```bash
   cd /path/to/DART/models/wrf_hydro/hydro_dart_py
   pip install .
   ```

3. **Set up the experiment** for one subbasin:

   ```bash
   cd /path/to/DART/models/wrf_hydro/python/experiment
   python setup_filter_experiment.py /path/to/this/repo/Mckenzie_River/Mckenzie_River.yaml
   ```

   This builds or links the DART and WRF-Hydro executables, builds the ensemble with `ens_setup_NWM_channel-only.py`, creates the initial ensemble with DART `filter`, and links the scripts listed in `noise_function_files` into every member folder.

4. **Run** from the `run_dir` set in the yaml:

   ```bash
   cd /path/to/run_dir
   python run_filter_experiment.py
   ```

   Setup also writes a `submit_filter_experiment.sh` there. The upstream template uses PBS directives, so on a Slurm cluster adapt its header or call `run_filter_experiment.py` from your own batch script.

## License

This repository is released under the Apache License 2.0. See [LICENSE](LICENSE).

## Contact

Fatemeh Shirkhanloo, Hydrologic Modeling and Assimilation Lab, Portland State University (fatemehs@pdx.edu)

Corresponding author: Peyman Abbaszadeh (pabbaszadeh@pdx.edu)
