import numpy

from ipie.config import config
from ipie.utils.backend import arraylib as xp
from ipie.utils.backend import cast_to_device, qr, qr_mode, synchronize
from ipie.walkers.base_walkers import BaseWalkers
#from ipie.addons.eph.trial_wavefunction.toyozawa import ToyozawaTrial

class EPhWalkers(BaseWalkers):
    """Class tailored to el-ph models where keeping track of phonon overlaps is
    required. Each walker carries along its Slater determinants a phonon 
    displacement vector, self.x.
    
    Parameters
    ----------
    initial_walker :
        Walker that we start the simulation from. Ideally chosen according to 
        the trial.
    nup : 
        Number of electrons in up-spin space.
    ndown :
        Number of electrons in down-spin space.
    nbasis :
        Number of sites in the 1D Holstein chain.
    nwalkers : 
        Number of walkers in the simulation.
    verbose : 
        Print level.
    """
    def __init__(
        self, 
        initial_walker: numpy.ndarray,
        nup: int,
        ndown: int,
        nbasis: int,
        nwalkers: int,
        verbose: bool = False
    ):

        self.nup = nup
        self.ndown = ndown
        self.nbasis = nbasis


        super().__init__(nwalkers, verbose=verbose)

        self.weight = numpy.ones(self.nwalkers, dtype=numpy.complex128)

        self.x = xp.array(
            [initial_walker[:,0].copy() for iw in range(self.nwalkers)],
            dtype=xp.complex128
        )
        self.x = numpy.squeeze(self.x)
 
        self.phia = xp.array(
            [initial_walker[:, 1 : self.nup+1].copy() for iw in range(self.nwalkers)],
            dtype=xp.complex128,
        )

        self.phib = xp.array(
            [initial_walker[:, self.nup+1 : self.nup+self.ndown+1].copy() for iw in range(self.nwalkers)],
            dtype=xp.complex128,
        )
       
        self.buff_names += ["phia", "phib", "x"]

        self.buff_size = round(self.set_buff_size_single_walker() / float(self.nwalkers))
        self.walker_buffer = numpy.zeros(self.buff_size, dtype=numpy.complex128)

    def build(self, trial):
        """Allocates memory for computation of overlaps throughout the 
        simulation.
        
        Parameters
        ----------
        trial : class
            Trial wavefunction object.
        """

        if hasattr(trial, "nperms"):
            shape = (self.nwalkers, trial.nperms)
        else:
            shape = self.nwalkers

        self.ph_ovlp = numpy.zeros(shape, dtype=numpy.complex128)
        self.el_ovlp = numpy.zeros(shape, dtype=numpy.complex128)
        self.total_ovlp = numpy.zeros(shape, dtype=numpy.complex128)

        self.buff_names += ['total_ovlp']
        self.buff_size = round(self.set_buff_size_single_walker() / float(self.nwalkers))
        self.walker_buffer = numpy.zeros(self.buff_size, dtype=numpy.complex128)

        trial.calc_overlap(self) 

    def cast_to_cupy(self, verbose=False):
        cast_to_device(self, verbose)

    def reortho(self):
        """reorthogonalise walkers. This function is mostly from BaseWalkers,
        with the exception that it adjusts all overlaps, possibly of numerous 
        coherent states.

        Parameters
        ----------
        """
        if config.get_option("use_gpu"):
            return self.reortho_batched()
        ndown = self.ndown
        detR = []
        for iw in range(self.nwalkers):
            (self.phia[iw], Rup) = qr(self.phia[iw], mode=qr_mode)
            # TODO: FDM This isn't really necessary, the absolute value of the
            # weight is used for population control so this shouldn't matter.
            # I think this is a legacy thing.
            # Wanted detR factors to remain positive, dump the sign in orbitals.
            Rup_diag = xp.diag(Rup)
            signs_up = xp.sign(Rup_diag)
            self.phia[iw] = xp.dot(self.phia[iw], xp.diag(signs_up))

            # include overlap factor
            # det(R) = \prod_ii R_ii
            # det(R) = exp(log(det(R))) = exp((sum_i log R_ii) - C)
            # C factor included to avoid over/underflow
            log_det = xp.sum(xp.log(xp.abs(Rup_diag)))

            if ndown > 0:
                (self.phib[iw], Rdn) = qr(self.phib[iw], mode=qr_mode)
                Rdn_diag = xp.diag(Rdn)
                signs_dn = xp.sign(Rdn_diag)
                self.phib[iw] = xp.dot(self.phib[iw], xp.diag(signs_dn))
                log_det += sum(xp.log(abs(Rdn_diag)))

            detR += [xp.exp(log_det - self.detR_shift[iw])]
            self.log_detR[iw] += xp.log(detR[iw])
            self.detR[iw] = detR[iw]
            
            self.el_ovlp[iw, ...] = self.el_ovlp[iw, ...] / detR[iw]
            self.total_ovlp[iw, ...] = self.total_ovlp[iw, ...] / detR[iw]
            self.ovlp[iw] = self.ovlp[iw] / detR[iw]

        synchronize()
        return detR

    def reortho_batched(self):  # gpu version
        pass
