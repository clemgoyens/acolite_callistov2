## def acolite_run
## runs acolite processing for given settings file/dict, new version
## written by Quinten Vanhellemont, RBINS
## 2021-04-01
## modifications: 2021-04-14 (QV) added output to settings if not configured
##                2021-04-15 (QV) test/parse input files
##                2022-03-04 (QV) moved inputfile testing to inputfile_test
##                2023-03-29 (AD) modified for CS tiff

# AD
def cleaning_4_CS(output_folder, filetime, L2W_delete=False):
    import os
    import glob
    print("\n >> renaming for CALLISTO platform")

    nametime=filetime.strftime("%Y_%m_%d")
    all_files=glob.glob('{}/*{}*'.format(output_folder, nametime))

    print(all_files)
    # chl_file = [file for file in all_files if 'chl_' in file and '_CHL.tif' not in file][0]
    # spm_file = [file for file in all_files if 'SPM_' in file and '_SPM.tif' not in file][0]
    # tur_file = [file for file in all_files if 'TUR_' in file and '_TUR.tif' not in file][0]
    # print(chl_file)
    # print(spm_file)
    # print(tur_file)
    # image_date = "".join(spm_file.split('_')[2:5])
    # image_time = "".join(spm_file.split('_')[5:8])
    #
    # os.rename(f'{output_folder}/{chl_file}', f'{output_folder}/{chl_file[0:7]}_{image_date}T{image_time}_CHL.tif')
    # os.rename(f'{output_folder}/{spm_file}', f'{output_folder}/{spm_file[0:7]}_{image_date}T{image_time}_SPM.tif')
    # os.rename(f'{output_folder}/{tur_file}', f'{output_folder}/{tur_file[0:7]}_{image_date}T{image_time}_TUR.tif')

    if L2W_delete is False:
        L2W_files = [f for f in all_files if 'L2W' in f and 'nc' in f]
        for L2W_file in L2W_files:
            all_files.remove(L2W_file)

    all_files = [file for file in all_files if all(x not in file for x in ['L2R.nc','L2R_GLAD.nc','flag','chl_re_mishra','chl_oc3', 'SPM', 'TUR', 'rhos.png', 'rhot.png'])] # do not delete TUR, SPM, CHL
    print(f'\n > deleting files: {all_files}')
    for file in all_files:
        try:
            os.remove(f'{output_folder}/{file}')
        except:
            pass

def fillandcrop(tiffile, shp=None, maskthreshold=None,maxsd=20, siter=5, filext=""):
    # read shapefile
    import rasterio
    import rioxarray as rio
    import rasterio.mask
    import rasterio.plot
    from rasterio.fill import fillnodata
    import numpy as np
    from shapely.geometry import mapping
    import geopandas as gpd
    import os

    shapefile = gpd.read_file(shp)

    with rasterio.open(tiffile) as src:
        profile = src.profile
        arr = src.read(1)
        arr = np.where(arr > maskthreshold, np.nan, arr)
        arr_filled = fillnodata(arr, mask=src.read_masks(1), max_search_distance=maxsd, smoothing_iterations=siter)

    newtif_file = "{}_crop{}.tif".format(tiffile.split(".tif")[0],filext)

    with rasterio.open(newtif_file, 'w', **profile) as dest:
        dest.write_band(1, arr_filled)

    with rasterio.open(newtif_file) as src:
        out_image, out_transform = rasterio.mask.mask(src, shapefile.geometry.apply(mapping), crop=True)
        out_meta = src.meta

    out_meta.update({"driver": "GTiff",
                     "height": out_image.shape[1],
                     "width": out_image.shape[2],
                     "transform": out_transform})

    if os.path.isfile(newtif_file):
        os.remove(newtif_file)

    with rasterio.open(newtif_file, "w", **out_meta) as dest:
        dest.write(out_image)

def acolite_run(settings, inputfile=None, output=None):
    import glob, datetime, os
    import acolite as ac
    import rasterio
    import rioxarray as rio
    import rasterio.mask
    import rasterio.plot
    from rasterio.fill import fillnodata
    import numpy as np
    from shapely.geometry import mapping
    import geopandas as gpd
    import os
    import csv


    print('Running ACOLITE 4 CALLISTO - {}'.format(ac.version))
    ## time of processing start
    time_start = datetime.datetime.now()

    ## get user settings
    ## these are updated with sensor specific settings in acolite_l2r
    setu = ac.acolite.settings.parse(None, settings=settings, merge=False)
    if 'runid' not in setu: setu['runid'] = time_start.strftime('%Y%m%d_%H%M%S')
    if 'output' not in setu: setu['output'] = os.getcwd()
    if 'verbosity' in setu: ac.config['verbosity'] = int(setu['verbosity'])

    ## workaround for outputting rhorc and bt
    if 'l2w_parameters' in setu:
        if setu['l2w_parameters'] is not None:
            for par in setu['l2w_parameters']:
                if 'rhorc' in par: setu['output_rhorc'] = True
                if 'bt' == par[0:2]: setu['output_bt'] = True

    ## log file for l1r generation
    log_file = '{}/acolite_run_{}_log_file.txt'.format(setu['output'],setu['runid'])
    log = ac.acolite.logging.LogTee(log_file)
    print('Run ID - {}'.format(setu['runid']))

    ## earthdata credentials from settings file
    for k in ['EARTHDATA_u', 'EARTHDATA_p']:
        kv = setu[k] if k in setu else ac.config[k]
        if len(kv) == 0: continue
        os.environ[k] = kv

    ## set settings from launch_acolite
    if inputfile is not None: setu['inputfile'] = inputfile
    if output is not None: setu['output'] = output

    ## check if we have anything to do
    if 'inputfile' not in setu:
        print('Nothing to do. Did you provide a settings file or inputfile? Exiting.')
        return()
    else:
        nscenes = len(setu['inputfile'])

    ## get defaults settings for l1r processing
    setu_l1r = ac.acolite.settings.parse(None, settings=setu, merge=False)

    ## make list of lists to process, one list if merging tiles
    inputfile_list = ac.acolite.inputfile_test(setu['inputfile'])

    ## check if tiles need to be merged
    if 'merge_tiles' in setu:
        if setu['merge_tiles']:
            ## figure out whether multiple sets of tiles are given for merging
            ## e.g. through a text inputfile with multiple lines of comma separated scenes
            inputfile = [[]]
            for i in inputfile_list:
                if type(i) == list:
                    inputfile.append(i)
                else:
                    inputfile[0].append(i)
            inputfile_list = [i for i in inputfile if len(i) > 0]
    nruns = len(inputfile_list)

    ## track processed scenes
    processed = {}
    ## run through bundles to process
    for ni in range(nruns):
        ## bundle to process
        bundle = inputfile_list[ni]
        processed[ni] = {'input': bundle}

        ## save user settings
        settings_file = '{}/acolite_run_{}_l1r_settings_user.txt'.format(setu_l1r['output'],setu_l1r['runid'])
        ac.acolite.settings.write(settings_file, setu_l1r)

        ## run l1 convert
        ret = ac.acolite.acolite_l1r(bundle, setu_l1r)
        if len(ret) == 0: continue
        l1r_files, l1r_setu = ret
        processed[ni]['l1r'] = l1r_files

        ## save all used settings
        settings_file = '{}/acolite_run_{}_l1r_settings.txt'.format(l1r_setu['output'],l1r_setu['runid'])
        ac.acolite.settings.write(settings_file, l1r_setu)

        ## do atmospheric correction
        l2r_files, l2t_files = [], []
        l2w_files = []
        for l1r in l1r_files:
            gatts = ac.shared.nc_gatts(l1r)
            if 'acolite_file_type' not in gatts: gatts['acolite_file_type'] = 'L1R'
            if l1r_setu['l1r_export_geotiff']: ac.output.nc_to_geotiff(l1r, match_file = l1r_setu['export_geotiff_match_file'],
                                                            cloud_optimized_geotiff = l1r_setu['export_cloud_optimized_geotiff'],
                                                            skip_geo = l1r_setu['export_geotiff_coordinates'] is False)
            if l1r_setu['l1r_export_geotiff_rgb']: ac.output.nc_to_geotiff_rgb(l1r, settings = l1r_setu)

            ## rhot RGB
            if l1r_setu['rgb_rhot']:
                l1r_setu_ = {k: l1r_setu[k] for k in l1r_setu}
                l1r_setu_['rgb_rhos'] = False
                ac.acolite.acolite_map(l1r, settings = l1r_setu_, plot_all=False)

            ## do VIS-SWIR atmospheric correction
            if l1r_setu['atmospheric_correction']:
                if gatts['acolite_file_type'] == 'L1R':
                    ## run ACOLITE
                    ret = ac.acolite.acolite_l2r(l1r, settings = setu, verbosity = ac.config['verbosity'])
                    if len(ret) != 2: continue
                    l2r, l2r_setu = ret
                else:
                    l2r = '{}'.format(l1r)
                    l2r_setu = ac.acolite.settings.parse(gatts['sensor'], settings=setu)

                if (l2r_setu['adjacency_correction']):
                    ret = None
                    ## acstar3 adjacency correction
                    if (l2r_setu['adjacency_method']=='acstar3'):
                        ret = ac.adjacency.acstar3.acstar3(l2r, setu = l2r_setu, verbosity = ac.config['verbosity'])
                    ## GLAD
                    if (l2r_setu['adjacency_method']=='glad'):
                        ret = ac.adjacency.glad.glad_l2r(l2r, verbosity = ac.config['verbosity'])
                    l2r = [] if ret is None else ret

                ## if we have multiple l2r files
                if type(l2r) is not list: l2r = [l2r]
                l2r_files+=l2r

                if l2r_setu['l2r_export_geotiff']:
                    for ncf in l2r:
                        ac.output.nc_to_geotiff(ncf, match_file = l2r_setu['export_geotiff_match_file'],
                                                cloud_optimized_geotiff = l1r_setu['export_cloud_optimized_geotiff'],
                                                skip_geo = l2r_setu['export_geotiff_coordinates'] is False)

                        if l2r_setu['l2r_export_geotiff_rgb']: ac.output.nc_to_geotiff_rgb(ncf, settings = l2r_setu)


                ## make rgb rhos maps
                if l2r_setu['rgb_rhos']:
                    l2r_setu_ = {k: l1r_setu[k] for k in l2r_setu}
                    l2r_setu_['rgb_rhot'] = False
                    for ncf in l2r:
                        ac.acolite.acolite_map(ncf, settings = l2r_setu_, plot_all=False)

                ## compute l2w parameters
                if l2r_setu['l2w_parameters'] is not None:
                    if type(l2r_setu['l2w_parameters']) is not list: l2r_setu['l2w_parameters'] = [l2r_setu['l2w_parameters']]
                    for ncf in l2r:
                        ret = ac.acolite.acolite_l2w(ncf, settings=l2r_setu)
                        l2w_file_path=ret
                        if ret is not None:
                            if l2r_setu['l2w_export_geotiff']: ac.output.nc_to_geotiff(ret, match_file = l2r_setu['export_geotiff_match_file'],
                                                                            cloud_optimized_geotiff = l1r_setu['export_cloud_optimized_geotiff'],
                                                                            skip_geo = l2r_setu['export_geotiff_coordinates'] is False)
                            l2w_files.append(ret)

                            ## make l2w maps
                            if l2r_setu['map_l2w']:
                                ac.acolite.acolite_map(ret, settings=l2r_setu)

            ## run TACT thermal atmospheric correction
            if l1r_setu['tact_run']:
                ret = ac.tact.tact_gem(l1r, output = l1r_setu['output'], verbosity=ac.config['verbosity'],
                                            output_atmosphere = l1r_setu['tact_output_atmosphere'],
                                            output_intermediate = l1r_setu['tact_output_intermediate'])
                if ret != ():
                    l2t_files.append(ret)
                    if l1r_setu['l2t_export_geotiff']: ac.output.nc_to_geotiff(ret, match_file = l1r_setu['export_geotiff_match_file'],
                                                                               cloud_optimized_geotiff = l1r_setu['export_cloud_optimized_geotiff'],
                                                                               skip_geo = l1r_setu['export_geotiff_coordinates'] is False)

                    ## make l2t maps
                    if l1r_setu['tact_map']: ac.acolite.acolite_map(ret, settings=l1r_setu)

        if len(l2r_files) > 0: processed[ni]['l2r'] = l2r_files
        if len(l2t_files) > 0: processed[ni]['l2t'] = l2t_files
        if len(l2w_files) > 0: processed[ni]['l2w'] = l2w_files

    ## reproject data
    try:
        project = l1r_setu['output_projection']
    except:
        project = False
    if project:
        for output in l1r_setu['reproject_outputs']:
            otype = output.lower()
            pkeys = processed.keys()
            for i in pkeys:
                reprojected = []
                if otype not in processed[i]: continue
                for ncf in processed[i][otype]:
                    ncfo = ac.output.project_acolite_netcdf(ncf, settings=settings)
                    if ncfo == (): continue
                    reprojected.append(ncfo)

                    ## make rgb  maps
                    if (otype == 'l1r') & (l1r_setu['rgb_rhot']):
                        l1r_setu_ = {k: l1r_setu[k] for k in l1r_setu}
                        l1r_setu_['rgb_rhos'] = False
                        ac.acolite.acolite_map(ncfo, settings = l1r_setu_, plot_all=False)
                    ## make rgb  maps
                    if (otype == 'l2r') & (l1r_setu['rgb_rhos']):
                        l1r_setu_ = {k: l1r_setu[k] for k in l1r_setu}
                        l1r_setu_['rgb_rhot'] = False
                        ac.acolite.acolite_map(ncfo, settings = l1r_setu_, plot_all=False)

                    ## make other  maps
                    if (otype == 'l2w') & (l1r_setu['map_l2w']):
                        l1r_setu_ = {k: l1r_setu[k] for k in l1r_setu}
                        l1r_setu_['rgb_rhos'] = False
                        l1r_setu_['rgb_rhot'] = False
                        ac.acolite.acolite_map(ncfo, settings = l1r_setu_, plot_all=True)

                    ## output geotiffs
                    if '{}_export_geotiff'.format(otype) in l1r_setu:
                        if l1r_setu['{}_export_geotiff'.format(otype)]:
                            ac.output.nc_to_geotiff(ncfo, match_file = l1r_setu['export_geotiff_match_file'],
                                                                        cloud_optimized_geotiff = l1r_setu['export_cloud_optimized_geotiff'],
                                                                        skip_geo = l1r_setu['export_geotiff_coordinates'] is False)
                    ## output rgb geotiff
                    if '{}_export_geotiff_rgb'.format(otype) in l1r_setu:
                        if l1r_setu['{}_export_geotiff_rgb'.format(otype)]:
                            ac.output.nc_to_geotiff_rgb(ncfo, settings = l1r_setu)
                processed[i]['{}_reprojected'.format(otype)] = reprojected
    ## end reproject data


    # AD
    # update files for CS platform
    print(processed[0].keys())
    for key in [key for key in processed[0].keys() if key in ['l1r', 'l2r', 'l2w']]:
        print(processed)
        file = processed[0][key][0]
        output_folder = os.path.dirname(file)

    filetime=datetime.datetime.strptime(os.path.basename(processed[0]['input']).split("_")[2], "%Y%m%dT%H%M%S")

    try:
        mask= "{}/data/shapefiles/{}".format( os.path.dirname(ac.code_path),setu['mask'])
        print(mask)
    except KeyError:
        mask=None
    print(mask)

    cleaning_4_CS(output_folder, filetime, L2W_delete=False)


    nametime=filetime.strftime("%Y_%m_%d")
    tiffiles=glob.glob('{}/*{}*chl_re_mishra*.tif'.format(output_folder, nametime))
    tiffiles.extend(glob.glob('{}/*{}*chl_re_mishra.tif'.format(output_folder, nametime)))
    tiffiles.extend(glob.glob('{}/*{}*chl_oc3_*.tif'.format(output_folder, nametime)))
    tiffiles.extend(glob.glob('{}/*{}*chl_oc3.tif'.format(output_folder, nametime)))

    print(l2r_setu['mask_and_fill'])
    if l2r_setu['mask_and_fill']:
        thr=l2r_setu['fill_mask_thr']
        maxsd=l2r_setu['fill_maximum_search_dist']
        siter=l2r_setu['fill_smoothing_distance']
        #maxsd = 20, siter = 5

#        def fillandcrop(tiffile, shp=None, maskthreshold=None, maxsd=20, siter=5, filext=""):

        [fillandcrop(tiffile=f, shp=mask, maskthreshold=thr,maxsd=maxsd,siter=siter) for f in tiffiles]

        if l2r_setu['output_stats']:
            shapefile = gpd.read_file(mask)
            # Get list of geometries for all features in vector file
            geom = [shapes for shapes in shapefile.geometry]

            # read oc3 crop file:
            files = glob.glob("{}/*{}*_GLAD_chl_oc3_*_crop.tif".format(output_folder, nametime))
            print(files)
            ds = rio.open_rasterio(files[0], masked=True).squeeze()

            # Open example raster
            raster = rasterio.open(r"{}".format(files[0]))
            # Rasterize vector using the shape and coordinate system of the raster
            rasterized = rasterio.features.rasterize(geom,
                                                     out_shape=raster.shape,
                                                     fill=0,
                                                     out=None,
                                                     transform=raster.transform,
                                                     all_touched=False,
                                                     default_value=1,
                                                     dtype=None)
            totpix=rasterized.sum()
            vals = ds.values
            stat_names = ['Percentage valid pixels','mean', 'median', 'std', 'var', 'min', 'max', '80p', '85p', '90p', '95p', '99p']
            stat_units = ['%','ug/l', 'ug/l', 'ug/l', 'ug/l', 'ug/l', 'ug/l', 'ug/l', 'ug/l', 'ug/l', 'ug/l', 'ug/l']

            validpix=np.count_nonzero(~np.isnan(ds.values))

            stats = np.array([validpix/totpix*100, np.nanmean(vals), np.nanmedian(vals),
                              np.nanstd(vals),
                              np.nanvar(vals),
                              np.nanmin(vals),
                              np.nanmax(vals),
                              np.nanpercentile(vals, 80),
                              np.nanpercentile(vals, 85),
                              np.nanpercentile(vals, 90),
                              np.nanpercentile(vals, 95),
                              np.nanpercentile(vals, 99)])

            stats_ = ["{}:{:0.2f} {}".format(stat_names[i], stats[i], stat_units[i]) for i in range(0, len(stats))]
            stats_="Statistics for image {}:, {}".format(os.path.basename(files[0]),(", ").join(stats_))

    #with open('{}/alert_{}.csv'.format(output_folder, nametime), 'w', newline='') as alert:
    with open('{}/alert.csv'.format(output_folder), 'w', newline='') as alert:
        alert.write(stats_)
        alert.close()

    print('\n finished deleting files ') # debug


        ## end processing loop
    log.__del__()

    ## remove files
    for ni in processed:
        for level in ['l1r', 'l2r', 'l2t', 'l2w']:
            if level not in processed[ni]: continue
            if '{}_delete_netcdf'.format(level) not in l1r_setu: continue
            if l1r_setu['{}_delete_netcdf'.format(level)]:
                ## run through images and delete them
                for f in processed[ni][level]:
                    try:
                        os.remove(f)
                        ## also delete pan file if it exists
                        if level == 'l1r':
                            panf = f.replace('_L1R.nc', '_L1R_pan.nc')
                            if os.path.exists(panf):
                                os.remove(panf)
                    except: #already deleted
                        pass
                ## replace by empty list
                processed[ni][level] = []

    ## remove log and settings files
    try:
        delete_text = l1r_setu['delete_acolite_run_text_files']
        op, ri = l1r_setu['output'], l1r_setu['runid']
    except:
        delete_text = False if 'delete_acolite_run_text_files' not in setu_l1r else setu_l1r[
            'delete_acolite_run_text_files']
        op, ri = setu_l1r['output'], setu_l1r['runid']

    if delete_text:
        tfiles = glob.glob('{}/acolite_run_{}_*.txt'.format(op, ri))
        for tf in tfiles:
            os.remove(tf)

    return(processed)
