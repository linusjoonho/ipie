from ipie.estimators.estimator_base import EstimatorBase
import numpy as np


class PhaseEstimatorFP(EstimatorBase):
    def __init__(self):
        super().__init__()
        self._data = {
            "PhaseRealNumer": 0.0,
            "PhaseImagNumer": 0.0,
            "PhaseDenom": 0.0,
        }

        self.scalar_estimator = True
        self._shape = (len(self.names),)
        self._data_index = {k: i for i, k in enumerate(list(self._data.keys()))}
        self.print_to_stdout = True
        self._ascii_filename = None


    def compute_estimator(self, system, walkers, hamiltonian, trial):
        weighted_phase = np.sum(walkers.weight * walkers.phase)
        self._data["PhaseRealNumer"] = weighted_phase.real
        self._data["PhaseImagNumer"] = weighted_phase.imag
        self._data["PhaseDenom"] = np.sum(walkers.weight)

        return self.data

    
    def get_index(self, name):
        index = self._data_index.get(name, None)
        if index is None:
            raise RuntimeError(f"Unknown estimator {name}")
        return index