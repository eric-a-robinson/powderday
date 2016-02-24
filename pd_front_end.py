#Code:  pd_front_end.py

#=========================================================
#IMPORT STATEMENTS
#=========================================================

import sys
script,pardir,parfile,modelfile = sys.argv
import numpy as np
import scipy.interpolate
import scipy.ndimage
import os.path
import copy
import pdb,ipdb

from hyperion.model import Model
import matplotlib as mpl
import matplotlib.pyplot as plt
from hyperion.model import ModelOutput
import h5py


import yt
from yt.units.yt_array import YTQuantity

sys.path.insert(0,pardir)
par = __import__(parfile)
model = __import__(modelfile)


import config as cfg
cfg.par = par #re-write cfg.par for all modules that read this in now
cfg.model = model

from astropy.table import Table
from astropy.io import ascii


from front_ends.front_end_controller import stream
from grid_construction import yt_octree_generate,grid_coordinate_boost,grid_center
import SED_gen as sg
from find_order import *
import powderday_test_octree as pto
import hyperion_octree_stats as hos
import error_handling as eh
import backwards_compatibility as bc

from m_control_tools import *
from image_processing import add_transmission_filters
#=========================================================
#CHECK FOR THE EXISTENCE OF A FEW CRUCIAL FILES FIRST
#=========================================================

eh.file_exist(model.hydro_dir+model.Gadget_snap_name)
eh.file_exist(par.dustdir+par.dustfile)


#=========================================================
#Enforce Backwards Compatibility for Non-Critical Variables
#=========================================================
cfg.par.FORCE_RANDOM_SEED,cfg.par.BH_SED,cfg.par.IMAGING,cfg.par.SED,cfg.par.IMAGING_TRANSMISSION_FILTER = bc.variable_set()

#=========================================================
#GRIDDING
#=========================================================


print 'Octree grid is being generated by yt'

fname = cfg.model.hydro_dir+cfg.model.Gadget_snap_name
field_add,ds = stream(fname)

#figure out which tributary we're going to

ds_type = ds.dataset_type 
#define the options dictionary
options = {'gadget_hdf5':m_control_sph,
           'tipsy':m_control_sph,
           'enzo_packed_3d':m_control_enzo}

m_gen = options[ds_type]()
m,xcent,ycent,zcent,dx,dy,dz,pf,boost = m_gen(fname,field_add)





#Get dust wavelengths. This needs to preceed the generation of sources
#for hyperion since the wavelengths of the SEDs need to fit in the
#dust opacities.

df = h5py.File(cfg.par.dustdir+cfg.par.dustfile,'r')
o = df['optical_properties']
df_nu = o['nu']
df_chi = o['chi']

df.close()


  


#add sources to hyperion
ad = pf.all_data()
stars_list,diskstars_list,bulgestars_list = sg.star_list_gen(boost,xcent,ycent,zcent,dx,dy,dz,pf,ad)
nstars = len(stars_list)




from source_creation import add_newstars,add_binned_seds,BH_source_add

if cfg.par.BH_SED == True: BH_source_add(m,pf,df_nu)


#figure out N_METAL_BINS:
fsps_metals = np.loadtxt(cfg.par.metallicity_legend)
N_METAL_BINS = len(fsps_metals)

if par.FORCE_BINNING == False:
    stellar_nu,stellar_fnu,disk_fnu,bulge_fnu = sg.allstars_sed_gen(stars_list,diskstars_list,bulgestars_list)
    m=add_newstars(df_nu,stellar_nu,stellar_fnu,disk_fnu,bulge_fnu,stars_list,diskstars_list,bulgestars_list,m)
    

#potentially write the stellar SEDs to a npz file
    if par.STELLAR_SED_WRITE == True:
        np.savez('stellar_seds.npz',par.COSMOFLAG,stellar_nu,stellar_fnu,disk_fnu,bulge_fnu)
        
else:
#note - the generation of the SEDs is called within
#add_binned_seds itself, unlike add_newstars, which requires
#that sg.allstars_sed_gen() be called first.
    
    m=add_binned_seds(df_nu,stars_list,diskstars_list,bulgestars_list,m)




nstars = len(stars_list)
nstars_disk = len(diskstars_list)
nstars_bulge = len(bulgestars_list)


   

    

if par.SOURCES_IN_CENTER == True:
    for i in range(nstars):
        stars_list[i].positions[:] = 0
        bulgestars_list[i].positions[:] = 0
        diskstars_list[i].positions[:] = 0 






print 'Done adding Sources'

print 'Setting up Model'
m_imaging = copy.deepcopy(m)

if cfg.par.SED == True:
    #set up the SEDs and images
    m.set_raytracing(True)
    m.set_n_photons(initial=par.n_photons_initial,imaging=par.n_photons_imaging,
                    raytracing_sources=par.n_photons_raytracing_sources,raytracing_dust=par.n_photons_raytracing_dust)
    m.set_n_initial_iterations(7)
    m.set_convergence(True,percentile=99.,absolute=1.01,relative=1.01)
    

    sed = m.add_peeled_images(sed = True,image=False)
    sed.set_wavelength_range(250,0.001,1000.)
    sed.set_viewing_angles(np.linspace(0,90,par.NTHETA).tolist()*par.NPHI,np.repeat(np.linspace(0,90,par.NPHI),par.NPHI))
    sed.set_track_origin('basic')
    
    print 'Beginning RT Stage'
    #Run the Model
    m.write(model.inputfile+'.sed',overwrite=True)
    m.run(model.outputfile+'.sed',mpi=True,n_processes=par.n_processes,overwrite=True)



#see if the variable exists to make code backwards compatible

if cfg.par.IMAGING == True:
    #read in the filters file
    filters = np.loadtxt(par.filter_file)
    print "Beginning Monochromatic Imaging RT"



    
    
    if cfg.par.IMAGING_TRANSMISSION_FILTER == False:
        m_imaging.set_monochromatic(True,wavelengths=filters)
        m_imaging.set_raytracing(True)
        m_imaging.set_n_photons(initial = par.n_photons_initial,
                                imaging_sources = par.n_photons_imaging,
                                imaging_dust =  par.n_photons_imaging,
                                raytracing_sources=par.n_photons_raytracing_sources,
                                raytracing_dust = par.n_photons_raytracing_dust)
       
    else:
        m_imaging.set_n_photons(initial=par.n_photons_initial,imaging=par.n_photons_imaging)

    m_imaging.set_n_initial_iterations(7)
    m_imaging.set_convergence(True,percentile=99.,absolute=1.01,relative=1.01)

    image = m_imaging.add_peeled_images(sed = True, image = True)
    if cfg.par.IMAGING_TRANSMISSION_FILTER == True:
        add_transmission_filters(image)
        
    image.set_viewing_angles(np.linspace(0,90,par.NTHETA).tolist()*par.NPHI,np.repeat(np.linspace(0,90,par.NPHI),par.NPHI))
    image.set_track_origin('basic')
    image.set_image_size(cfg.par.npix_x,cfg.par.npix_y)
    image.set_image_limits(-dx,dx,-dy,dy)
   
    m_imaging.write(model.inputfile+'.image',overwrite=True)
    m_imaging.run(model.outputfile+'.image',mpi=True,n_processes=par.n_processes,overwrite=True)
   












