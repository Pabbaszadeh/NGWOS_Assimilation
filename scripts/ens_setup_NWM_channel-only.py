nudge_keys = wrf_hydro_ens_sim.members[0].base_hydro_namelist['nudging_nlist'].keys()
for kk in nudge_keys:
    att_tuple = ('base_hydro_namelist', 'nudging_nlist', kk)
    values = ''
    wrf_hydro_ens_sim.set_member_diffs(att_tuple, values)



att_tuple = ('base_hrldas_namelist', 'noahlsm_offline', 'indir')
values = './FORCING_perturbed'
wrf_hydro_ens_sim.set_member_diffs(att_tuple, values)



att_tuple = ('base_hrldas_namelist', 'wrf_hydro_offline', 'forc_typ')
values = 9
wrf_hydro_ens_sim.set_member_diffs(att_tuple, values)



att_tuple = ('base_hydro_namelist', 'hydro_nlist', 'compound_channel')
values = True
wrf_hydro_ens_sim.set_member_diffs(att_tuple, values)



att_tuple = ('base_hydro_namelist', 'hydro_nlist', 'rst_dt')
values = 60
wrf_hydro_ens_sim.set_member_diffs(att_tuple, values)



att_tuple = ('base_hydro_namelist', 'hydro_nlist', 'out_dt')
values = 60
wrf_hydro_ens_sim.set_member_diffs(att_tuple, values)

att_tuple = ('base_hydro_namelist', 'hydro_nlist', 'output_channelbucket_influx')
values = 0
wrf_hydro_ens_sim.set_member_diffs(att_tuple, values)


