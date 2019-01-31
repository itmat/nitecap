import numpy

def BH_FDR(ps):
    ''' Benjamini-Hochberg FDR control

    Converts p values to q values'''
    # For the purposes of comparison, an implementation of Benjamini Hochberg correction
    sort_order = numpy.argsort(ps)

    adjusted = numpy.zeros(ps.shape)
    adjusted[sort_order] = numpy.array(ps)[sort_order]*len(ps)/numpy.arange(1,len(ps)+1)

    # Make monotone
    for i, r in enumerate(sort_order):
        adjusted[r] = min(numpy.min(adjusted[sort_order[i:]]), 1)

    return adjusted # the q-values

def FWER(tds, perm_tds):
    ''' Non-parametric FWER control through permutations

    Implements Westfall and Young (1993)'s FWER control method
    '''
    (N_PERMS, N_GENES) = perm_tds.shape

    sort_order = numpy.argsort(tds)

    # FWER (Westfall + Young 1993)
    p_hats = numpy.ones(N_GENES)
    for i, gene in enumerate(sort_order):
        p = 0
        for j in range(N_PERMS):
            perm_td = perm_tds[j]

            # For FWER control, compute genes at or higher than rank i
            any_higher_are_below_cutoff = numpy.any(perm_td[sort_order[i:]] <= tds[gene])
            p += 1/N_PERMS if any_higher_are_below_cutoff else 0

        p_hats[gene] = p
        p_hats[gene] = p_hats[sort_order[:i+1]].max() # make monotone
    return p_hats

def zero_nans(array):
    ''' Sets all nans in a numpy array to zero, works in-place

    Faster than numpy.nan_to_num, doesn't interfere with infinities
    and has a more descriptive name
    '''

    nans = numpy.isnan(array)
    array[nans] = 0
