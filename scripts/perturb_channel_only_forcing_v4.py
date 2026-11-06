#!/usr/bin/env python3

import argparse
import datetime
import f90nml
import importlib.util
import os
import pathlib
import sys
import numpy as np
import xarray as xa

# Channel-only (forc_typ = 9) forcing perturbation, with parameter multipliers.


#
#   0. LINK ORDER. parameter_restart.nc is built by create_parameter_restart_file.py
#      from a HYDRO_RST variable, so it inherits the model's internal channel
#      order, which is the Route_Link order. CHRTOUT forcing files are written in
#      feature_id order, and the two are NOT the same. 
#      this version reorders theta into CHRTOUT order using Route_Link `link` and the
#      `feature_id` of the forcing files.
#
#
#   1. --use_theta : the DART-estimated multipliers qSfcLatRunoffMult and
#      qBucketMult are read from this member's parameter_restart.<date>.nc and
#      applied to the channel fluxes before the stochastic noise. This is what
#      closes the state-parameter loop: WRF-Hydro cannot read the DART parameter
#      file itself, so the multipliers have to be applied to the channel forcing
#      that the model does read.
#
#
#   2. The multipliers are applied to the PRISTINE source forcing every cycle, never
#      to the previous cycle's perturbed forcing, so they cannot compound.


def import_noise_model(noise_file):
    spec = importlib.util.spec_from_file_location("noise_model", noise_file)
    noise_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(noise_module)
    return noise_module.noise_model


def read_theta(run_dir, model_time):
    """Read this member's current multipliers, as written by DART.

    Returns (theta_qSfcLatRunoff, theta_qBucket), each of length n_links.
    """
    fname = 'parameter_restart.' + model_time.strftime('%Y-%m-%d_%H:%M') + '.nc'
    path = pathlib.Path(run_dir) / fname

    if not path.exists():
        raise FileNotFoundError(
            'use_theta was requested but this cycle has no parameter restart: '
            + str(path)
        )

    with xa.open_dataset(str(path)) as ds:
        for needed in ['qSfcLatRunoffMult', 'qBucketMult']:
            if needed not in ds:
                raise KeyError(needed + ' not found in ' + str(path))
        theta_qsfclat = ds['qSfcLatRunoffMult'].values.astype('f4')
        theta_qbucket = ds['qBucketMult'].values.astype('f4')

    return theta_qsfclat, theta_qbucket


def build_theta_index(route_link_file, chrtout_file):
    """Map parameter/Route_Link order onto CHRTOUT feature_id order.

    Returns idx such that theta[idx] is aligned with the CHRTOUT arrays.
    """
    with xa.open_dataset(str(route_link_file)) as rl:
        link_ids = rl['link'].values
    with xa.open_dataset(str(chrtout_file)) as ch:
        if 'feature_id' not in ch.variables:
            raise KeyError('feature_id not found in ' + str(chrtout_file))
        feature_ids = ch['feature_id'].values

    if link_ids.size != feature_ids.size:
        raise ValueError('Route_Link has %d links but the forcing has %d'
                         % (link_ids.size, feature_ids.size))

    pos = {int(v): k for k, v in enumerate(link_ids)}
    missing = [int(f) for f in feature_ids if int(f) not in pos]
    if missing:
        raise ValueError('%d forcing feature_ids are absent from Route_Link, '
                         'first few: %s' % (len(missing), missing[:5]))

    idx = np.array([pos[int(f)] for f in feature_ids], dtype=int)
    identical = bool(np.array_equal(link_ids, feature_ids))
    return idx, identical


def perturb_channel_only_forcing(
    chrtout_file,
    qsfclat_perturb_func,
    qbucket_perturb_func,
    out_dir,
    seed: int = None,
    theta_qsfclat=None,
    theta_qbucket=None
):

    # Input.
    drop_list = ['streamflow', 'nudge', 'q_lateral', 'velocity']
    chrtout = xa.open_dataset(str(chrtout_file), engine="netcdf4",
                              drop_variables=drop_list)

    if 'qSfcLatRunoff' not in chrtout:
        chrtout.close()
        raise KeyError('qSfcLatRunoff not found in ' + str(chrtout_file))
    if 'qBucket' not in chrtout:
        chrtout.close()
        raise KeyError('qBucket not found in ' + str(chrtout_file))

    qsfclat = chrtout.qSfcLatRunoff.values
    qbucket = chrtout.qBucket.values

    # 1) Apply the DART-estimated multipliers to the pristine fluxes.
    if theta_qsfclat is not None:
        if qsfclat.shape[-1] != theta_qsfclat.shape[-1]:
            chrtout.close()
            raise ValueError(
                'theta length %d does not match forcing length %d in %s'
                % (theta_qsfclat.shape[-1], qsfclat.shape[-1], str(chrtout_file))
            )
        qsfclat = qsfclat * theta_qsfclat
        qbucket = qbucket * theta_qbucket

    # 2) Then the stochastic forcing noise, on top of the scaled flux.
    #    This set maintains metadata.
    chrtout.qSfcLatRunoff.values = qsfclat_perturb_func(qsfclat, seed=seed)
    chrtout.qBucket.values = qbucket_perturb_func(qbucket, seed=seed)

    # Output.
    
    chrtout.qSfcLatRunoff.encoding.update({'_FillValue': None})
    chrtout.qBucket.encoding.update({'_FillValue': None})
    chrtout_basename = os.path.basename(chrtout_file)
    paths = out_dir / chrtout_basename

    chrtout.to_netcdf(paths, mode='w')
    chrtout.close()
    return paths


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description='Apply parameter multipliers and noise to the channel-only '
                    'forcing files implied by the current run.'
    )

    parser.add_argument('--run_dir', metavar='run_dir', type=str, nargs=1,
                        default=None)
    parser.add_argument('--source_forcing_dir', metavar='source_forcing_dir',
                        type=str, nargs=1,
                        help='This dir should exist in the run_dir.')
    parser.add_argument('--perturb_forcing_dir', metavar='perturb_forcing_dir',
                        type=str, nargs=1,
                        help='This should just be the basename, the dir will be placed in the run_dir.')
    parser.add_argument('--qsfclat_perturb_func', metavar='qsfclat_perturb_func',
                        type=str, nargs=1,
                        help='A /path/to/file.py containing noise_model(x, seed).')
    parser.add_argument('--qbucket_perturb_func', metavar='qbucket_perturb_func',
                        type=str, nargs=1,
                        help='As for qsfclat_perturb_func.')
    parser.add_argument('--seed', metavar='seed_for_np.random', type=int,
                        nargs=1, help='seed to control random variables.',
                        default=None)
    parser.add_argument('--route_link', metavar='route_link', type=str, nargs=1,
                        default=None,
                        help='/path/to/Route_Link.nc, required with --use_theta. '
                             'Used to map the parameter file link order onto the '
                             'CHRTOUT feature_id order.')
    parser.add_argument('--use_theta', action='store_true',
                        help='Scale qSfcLatRunoff and qBucket by the multipliers '
                             'in this member/cycle parameter_restart.<date>.nc '
                             'before adding noise. Omit to add the noise only')

    args = parser.parse_args()

    run_dir = args.run_dir
    if run_dir is None:
        run_dir = os.getcwd()
    else:
        run_dir = run_dir[0]

    source_forcing_dir = args.source_forcing_dir[0]
    perturb_forcing_dir = args.perturb_forcing_dir[0]
    qsfclat_perturb_func = args.qsfclat_perturb_func[0]
    qbucket_perturb_func = args.qbucket_perturb_func[0]

    seed_arg = args.seed
    if seed_arg is not None and not isinstance(seed_arg, int):
        seed_arg = seed_arg[0]

    
    job_dir = sorted(pathlib.Path(run_dir).glob('job_*'))[-1]
    namelist_hrldas = f90nml.read(str(job_dir) + '/namelist.hrldas')

   
    ktime_key = set(namelist_hrldas['noahlsm_offline'].keys()) & set(['kday', 'khour'])
    ktime_key = list(ktime_key)[0]
    ktime_hour = int(namelist_hrldas['noahlsm_offline'][ktime_key])
    if ktime_key == 'kday':
        ktime_hour = ktime_hour * 24

    forcing_timestep = int(namelist_hrldas['noahlsm_offline']['forcing_timestep'])
    forcing_timestep_hour = forcing_timestep / (60 * 60)
    n_forcing_files = ktime_hour / forcing_timestep_hour
    if n_forcing_files != int(n_forcing_files):
        raise ValueError('ktime_hour / forcing_timestep_hour does not give integer')
    n_forcing_files = int(n_forcing_files)

    noahlsm_offline = namelist_hrldas['noahlsm_offline']
    model_time = datetime.datetime(
        int(noahlsm_offline['start_year']),
        int(noahlsm_offline['start_month']),
        int(noahlsm_offline['start_day']),
        int(noahlsm_offline['start_hour']),
        int(noahlsm_offline['start_min'])
    )

    
    forcing_basenames = \
        [(model_time + datetime.timedelta(hours=(tt + 1))).strftime('%Y%m%d%H%M')
         + '.CHRTOUT_DOMAIN1' for tt in range(n_forcing_files)]

    forcing_dir_existing = pathlib.PosixPath(run_dir) / source_forcing_dir
    forcing_dir_perturbed = pathlib.PosixPath(run_dir) / perturb_forcing_dir
    forcing_dir_perturbed.mkdir(parents=False, exist_ok=True)

    # The DART-estimated multipliers for this member, this cycle, reordered
    # from parameter/Route_Link order into the CHRTOUT feature_id order.
    theta_qsfclat = None
    theta_qbucket = None
    if args.use_theta:
        if args.route_link is None:
            raise ValueError('--use_theta requires --route_link /path/to/Route_Link.nc')
        theta_qsfclat, theta_qbucket = read_theta(run_dir, model_time)
        idx, identical = build_theta_index(
            args.route_link[0], forcing_dir_existing / forcing_basenames[0])
        theta_qsfclat = theta_qsfclat[idx]
        theta_qbucket = theta_qbucket[idx]
        print('theta @ %s  n_links=%d  reordered=%s  '
              'qSfcLatRunoffMult mean=%.4f  qBucketMult mean=%.4f'
              % (model_time.strftime('%Y-%m-%d_%H:%M'),
                 theta_qsfclat.shape[-1],
                 'no (orders already identical)' if identical else 'yes',
                 float(theta_qsfclat.mean()),
                 float(theta_qbucket.mean())))

    # Get the noise/perturbation functions
    qsfclat_perturb_func = import_noise_model(qsfclat_perturb_func)
    qbucket_perturb_func = import_noise_model(qbucket_perturb_func)

    # Loop over the forcing files
    for bb in forcing_basenames:

        if seed_arg is not None:
            seed = seed_arg
        else:
            
            member_number = int(pathlib.Path(run_dir).name.split('_')[1])
            the_time = datetime.datetime.strptime(bb.split('.')[0], '%Y%m%d%H%M')
            greg_time = the_time - datetime.datetime(1601, 1, 1)
            greg_time_min = greg_time.days * 24 * 60 + greg_time.seconds / 60
            seed = int(((greg_time_min % 10000000) * 100) + member_number)

        perturb_channel_only_forcing(
            forcing_dir_existing / bb,
            qsfclat_perturb_func,
            qbucket_perturb_func,
            forcing_dir_perturbed,
            seed,
            theta_qsfclat=theta_qsfclat,
            theta_qbucket=theta_qbucket
        )

    # replace with the new/perturbed forcing dir
    namelist_hrldas['noahlsm_offline']['indir'] = perturb_forcing_dir
    namelist_hrldas.write(str(job_dir) + '/namelist.hrldas', force=True)

    sys.exit(0)  
