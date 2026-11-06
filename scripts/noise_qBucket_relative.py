import numpy as np


def noise_model(x, seed: int=None):

    
    # Noise model for qBucket
    # 0) Additive noise,
    # 1) Zero-mean,
    # 2) frac: Standard deviation is a fraction of the value,
    # 3) minim: Truncated below at minim,
   
    frac = 0.4
    minim = 0.0


    if seed is not None:
        seed = (seed - sum([ord(ii) - 96 for ii in list('qbucket')])) % (2**32 - 1)
        np.random.seed(seed)

    std_dev_vec = np.multiply(frac, x)
    perturb_vec = np.add(x, np.random.normal(0.0, std_dev_vec))
    constrain_perturb_vec = np.fmax(perturb_vec, minim)

    return constrain_perturb_vec
