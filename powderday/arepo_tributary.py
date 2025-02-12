from __future__ import print_function
import numpy as np
import yt

from hyperion.model import Model
import matplotlib as mpl
mpl.use('Agg')
import powderday.config as cfg

from powderday.grid_construction import arepo_vornoi_grid_generate
from hyperion.dust import SphericalDust

from powderday.helpers import energy_density_absorbed_by_CMB
from powderday.tributary_dust_add import active_dust_add


def arepo_m_gen(fname,field_add):

    reg,ds,dustdens = arepo_vornoi_grid_generate(fname,field_add)

    xcent = ds.quan(cfg.model.x_cent,'code_length').to('cm') #proper cm
    ycent = ds.quan(cfg.model.y_cent,'code_length').to('cm')
    zcent = ds.quan(cfg.model.z_cent,'code_length').to('cm')
    
    boost = np.array([xcent,ycent,zcent])
    print ('[arepo_tributary/vornoi_m_gen]:  boost = ',boost)

    #========================================================================
    #Initialize Hyperion Model
    #========================================================================

    m = Model()
    
    #save in the m__dict__ that we're in a voronoi geometry
    m.__dict__['grid_type']='vor'


    #because we boost the stars to a [0,0,0] coordinate center, we
    #want to make sure our vornoi tesslation is created in the same manner.

    if cfg.par.otf_extinction==False:
        print("Computing Voronoi Tessellation on gas particles")
        particle_x = reg["gas","coordinates"][:,0].to('cm')
        particle_y = reg["gas","coordinates"][:,1].to('cm')
        particle_z = reg["gas","coordinates"][:,2].to('cm')
    else:
        print("Computing Voronoi Tessellation on PartType3 dust particles")
        particle_x = reg["dust","coordinates"][:,0].to('cm')
        particle_y = reg["dust","coordinates"][:,1].to('cm')
        particle_z = reg["dust","coordinates"][:,2].to('cm')

    #just for the sake of symmetry, pass on a dx,dy,dz since it can be
    #used optionally downstream in other functions.
    dx = 2.* ds.quan(cfg.par.zoom_box_len,'kpc').to('cm')
    dy = 2.* ds.quan(cfg.par.zoom_box_len,'kpc').to('cm')
    dz = 2.* ds.quan(cfg.par.zoom_box_len,'kpc').to('cm')

    print ('[arepo_tributary] boost = ',boost)
    print ('[arepo_tributary] xmin (pc)= ',(xcent-dx/2.).to('pc'))
    print ('[arepo_tributary] xmax (pc)= ',(xcent+dx/2.).to('pc'))
    print ('[arepo_tributary] ymin (pc)= ',(ycent-dy/2.).to('pc'))
    print ('[arepo_tributary] ymax (pc)= ',(ycent+dy/2.).to('pc'))
    print ('[arepo_tributary] zmin (pc)= ',(zcent-dz/2.).to('pc'))
    print ('[arepo_tributary] zmax (pc)= ',(zcent+dz/2.).to('pc'))

    x_pos_boost = (particle_x-xcent).to('cm')
    y_pos_boost = (particle_y-ycent).to('cm')
    z_pos_boost = (particle_z-zcent).to('cm')
    
    m.set_voronoi_grid(x_pos_boost.value, y_pos_boost.value, z_pos_boost.value)

    #get CMB:
    
    energy_density_absorbed=energy_density_absorbed_by_CMB()
    specific_energy = np.repeat(energy_density_absorbed.value,dustdens.shape)

    if cfg.par.otf_extinction==False:

        if cfg.par.PAH == True:
        
            # load PAH fractions for usg, vsg, and big (grain sizes)
            frac = cfg.par.PAH_frac

            # Normalize to 1
            total = np.sum(list(frac.values()))
            frac = {k: v / total for k, v in frac.items()}

            for size in frac.keys():
                d = SphericalDust(cfg.par.dustdir+'%s.hdf5'%size)
                if cfg.par.SUBLIMATION == True:
                    d.set_sublimation_temperature('fast',temperature=cfg.par.SUBLIMATION_TEMPERATURE)
                    #m.add_density_grid(dustdens * frac[size], cfg.par.dustdir+'%s.hdf5' % size)
                m.add_density_grid(dustdens*frac[size],d,specific_energy=specific_energy)
            m.set_enforce_energy_range(cfg.par.enforce_energy_range)
        else:
            d = SphericalDust(cfg.par.dustdir+cfg.par.dustfile)
            if cfg.par.SUBLIMATION == True:
                d.set_sublimation_temperature('fast',temperature=cfg.par.SUBLIMATION_TEMPERATURE)
            m.add_density_grid(dustdens,d,specific_energy=specific_energy)
        #m.add_density_grid(dustdens,cfg.par.dustdir+cfg.par.dustfile)  

    else: #instead of using a constant extinction law across the
          #entire galaxy, we'll compute it on a cell-by-cell bassis by
          #using information about the grain size distribution from
          #the simulation itself.

        ad = ds.all_data()
        nsizes = reg['PartType3','Dust_NumGrains'].shape[1]
        try:
            assert(np.sum(ad['PartType3','Dust_NumGrains']) > 0)
        except AssertionError:
            raise AssertionError("[arepo_tributary:] There are no dust grains in this simulation.  This can sometimes happen in an early snapshot of a simulation where the dust has not yet had time to form.")
        grid_of_sizes = reg['PartType3','Dust_NumGrains']
        active_dust_add(ds,m,grid_of_sizes,nsizes,dustdens,specific_energy)


    m.set_specific_energy_type('additional')



    
    return m,xcent,ycent,zcent,dx.value,dy.value,dz.value,reg,ds,boost
