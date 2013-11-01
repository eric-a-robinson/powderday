#Code:  pd_front_end.py

#outline:

#1. Generate Grid
#2. Run SPS + CLOUDY
#3. Generate Hyperion Model
#4. Run Hyperion


#=========================================================
#IMPORT STATEMENTS
#=========================================================




import numpy as np
from hyperion.model import Model
import matplotlib as mpl
import matplotlib.pyplot as plt
from hyperion.model import ModelOutput
import h5py

import constants as const
import parameters as par

import random
import pfh_readsnap
from grid_construction import *

from SED_gen import *
import sys

import os.path
#=========================================================
#GRIDDING
#=========================================================

if os.path.isfile(par.Auto_TF_file) == False:
    #only create the grid if the grid T/F file doesn't exist already

    if par.Manual_TF == True: 
        print 'Grid is coming from a Manually Set T/F Octree'
        refined = np.genfromtxt(par.Manual_TF_file,dtype = 'str')
        dustdens = np.loadtxt(par.Manual_density_file,dtype='float')

        #change refined T's to Trues and F's to Falses
    
        refined2 = []
        
        for i in range(len(refined)):
            if refined[i] == 'T':refined2.append(True)
            if refined[i] == 'F':refined2.append(False)
        
            refined = refined2

            print 'Manual grid finished reading in '


    elif par.GADGET_octree_gen == True:
        print 'Octree grid is being generated from the Gadget Snapshot'
        
        refined = gadget_logical_generate(par.Gadget_dir,par.Gadget_snap_num)
        
    elif par.YT_octree_gen == True:

        print 'Octree grid is being generated by YT'

     
        refined = yt_octree_generate(par.Gadget_snap_name,par.Gadget_dir,par.Gadget_snap_num)
        


else:
    print 'Grid already exists - no need to recreate it: '+ str(par.Auto_TF_file)
    print 'Instead - reading in the grid.'

    #read in the grid if the grid already exists.
    #reading in the refined:
    refined = np.genfromtxt(par.Auto_TF_file,dtype = 'str',skiprows=1)
    pos_data = np.loadtxt(par.Auto_positions_file,skiprows=1)
    xmin = pos_data[:,0]*const.pc*1.e3
    xmax = pos_data[:,1]*const.pc*1.e3
    ymin = pos_data[:,2]*const.pc*1.e3
    ymax = pos_data[:,3]*const.pc*1.e3
    zmin = pos_data[:,4]*const.pc*1.e3
    zmax = pos_data[:,5]*const.pc*1.e3
    
    xcent = np.mean([min(xmin),max(xmax)])
    ycent = np.mean([min(ymin),max(ymax)])
    zcent = np.mean([min(zmin),max(zmax)])

    #dx,dy,dz are the edges of the parent grid
    dx = (max(xmax)-min(xmin))/2.
    dy = (max(ymax)-min(ymin))/2.
    dz = (max(zmax)-min(zmin))/2.
                

    dustdens_data = np.loadtxt(par.Auto_dustdens_file,skiprows=1)
    dustdens = dustdens_data[:]

    #change refined T's to Trues and F's to Falses
    refined2 = []
    for i in range(len(refined)):
        if refined[i] == 'True':refined2.append(True)
        if refined[i] == 'False':refined2.append(False)
    refined = refined2


#end gridding


      
#generate the SEDs 

#stellar_nu,fnu are of shape (nstars,nlambda);
#stellar_mass is the mass of the star particles, and therefore
#(nstars) big.
#stellar_pos is (nstars,3) big



stellar_pos,stellar_masses,stellar_nu,stellar_fnu= new_sed_gen(par.Gadget_dir,par.Gadget_snap_num)
#generate the stellar masses and sizes 


nstars = stellar_nu.shape[0]




#========================================================================
#Initialize Hyperion Model
#========================================================================

m = Model()
if par.Grid_Type == 'Octree':
    m.set_octree_grid(xcent,ycent,zcent,
                      dx,dy,dz,refined)


m.add_density_grid(dustdens,par.dustfile)

#if par.Grid_Type == 'Cart'
    





#generate dust model. This needs to preceed the generation of sources
#for hyperion since the wavelengths of the SEDs need to fit in the dust opacities.

df = h5py.File(par.dustfile,'r')
o = df['optical_properties']
df_nu = o['nu']
df_chi = o['chi']

df.close()




#add sources to hyperion

for i in range(nstars):
    nu = stellar_nu[i,:]
    fnu = stellar_fnu[i,:]


    nu_inrange = np.logical_and(nu >= min(df_nu),nu <= max(df_nu))
    nu_inrange = np.where(nu_inrange == True)[0]
    nu = nu[nu_inrange]

    #reverse the arrays for hyperion
    nu = nu[::-1]
    fnu = fnu[::-1]

    #DEBUG - does fnu need to be scaled by the stellar mass since it's normalized for a single solar mass?
    fnu = fnu[nu_inrange]

    lum = np.absolute(np.trapz(fnu,x=nu))*stellar_masses[i]/const.msun #since stellar masses are in cgs, and we need them to be in msun
    
    m.add_spherical_source(luminosity = lum,
                           spectrum = (nu,fnu),
                           position = (stellar_pos[i,0],stellar_pos[i,1],stellar_pos[i,2]),
                           radius = par.stellar_softening_length*const.pc*1.e3)

print 'Done adding Sources'

print 'Setting up Model'
#set up the SEDs and images
m.set_raytracing(True)
m.set_n_photons(initial=1.e6,imaging=1.e6,
                raytracing_sources=1.e6,raytracing_dust=1.e6)
m.set_n_initial_iterations(5)


image = m.add_peeled_images(sed = True,image=False)
image.set_wavelength_range(250,0.01,5000.)
image.set_viewing_angles(np.linspace(0,90,par.NTHETA),np.repeat(20,par.NTHETA))
image.set_track_origin('basic')

print 'Beginning RT Stage'
#Run the Model
m.write('example.rtin')
m.run('example.rtout',mpi=True,n_processes=2)








print 'pdb.set_trace() at end of pd_front_end'
pdb.set_trace()






'''COMMENT STARTS HERE JUST TO NOT RUN THE REST OF CODE WHILE WE WORK ON GRIDDING 



#Make dustdens array as long as the refined array (with zero's where the Trues are)
dustdens2 = np.zeros(len(refined))
counter = 0
for i in range(len(refined)):
    if refined[i] == True: dustdens2[i] = 0
    if refined[i] == False: 
        dustdens2[i] = dustdens[counter]
        counter+=1
dustdens = dustdens2




m = Model()

par.dx *= 1e3*const.pc
par.dy *= 1e3*const.pc
par.dz *= 1e3*const.pc


m.set_octree_grid(par.x_cent,par.y_cent,par.z_cent,
                  par.dx,par.dy,par.dz,refined)






m.add_density_grid(dustdens,par.dustfile)




#=========================================================
#Add Sources
#=========================================================

m.add_spherical_source(luminosity = 1.e3*const.lsun,temperature = 6000., 
                       radius = 10.*const.rsun)


#debug 052313 - this only adds a few sources
for i in range(10):
    m.add_spherical_source(luminosity = 1e3*const.lsun,temperature = 6000.,
                           radius = 10.*const.rsun, 
                           position = [random.random()*par.dx,random.random()*par.dy,random.random()*par.dz])

for i in range(10):
     m.add_spherical_source(luminosity = 1e3*const.lsun,temperature = 6000.,
                           radius = 10.*const.rsun, 
                           position = [random.random()*-par.dx,random.random()*-par.dy,random.random()*-par.dz])
                           





#=========================================================
#Set RT Parameters
#=========================================================

m.set_raytracing(True)
m.set_n_photons(initial = 1.e5,imaging = 1.e5,
                raytracing_sources = 1.e5,raytracing_dust = 1.e5)


#DEBUG - need to make the number of iterations we run flexible
m.set_n_initial_iterations(5)



#=========================================================
#ADD THE SED INFORMATION YOU WANT
#=========================================================

if par.CALCULATE_SED == 1:
    
    image = m.add_peeled_images(sed = True,image = False)
    image.set_wavelength_range(par.n_wav,par.wav_min,par.wav_max)

    #DEBUG - the phi angles don't need to only be 0 degrees
    image.set_viewing_angles(np.linspace(0.,90.,par.N_viewing_angles),
                              np.repeat(0.,par.N_viewing_angles))

    image.set_track_origin('basic')


#=========================================================
#WRITE AND RUN THE MODEL
#=========================================================

m.write('dum.rtin')
m.run('dum.rtout',mpi=True,n_processes=3)




'''

