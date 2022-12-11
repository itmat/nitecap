import numpy
import scipy.stats
import statsmodels.api as sm

# TODO: remove this file once we migrate UPSIDE to the computation backend

def BH_FDR(ps):
    ''' Benjamini-Hochberg FDR control

    Converts p values to q values'''
    # For the purposes of comparison, an implementation of Benjamini Hochberg correction
    sort_order = numpy.argsort(ps)

    adjusted = numpy.zeros(ps.shape)
    adjusted[sort_order] = numpy.array(ps)[sort_order]*len(ps)/numpy.arange(1,len(ps)+1)

    # Make monotone, skipping NaNs
    m = 1;
    for i, r in enumerate(sort_order[::-1]):
        if numpy.isfinite(adjusted[r]):
            m = min(adjusted[r], m)
            adjusted[r] = m

    return adjusted # the q-values

def anova_on_groups(data, group_assignments):
    '''
    Perform an ANOVA test and return p-values

    `data`: an array of shape N x k. Each row is one measurement
    `group_assignments`: an array or list of length k, with categorical values.

    returns: array of shape N of p-values for test of equality of the categorical values
    '''

    #TODO: this and the abova anova function are likely now redundant
    # not sure this one is correct, probably should use the one above

    N_FEATURES = data.shape[0]
    N_MEASURES = data.shape[1]
    assert len(group_assignments) == N_MEASURES

    # Create design matrix (predictors)
    groups = numpy.array(list(set(group_assignments)))
    predictors = numpy.empty(shape=(len(groups), N_MEASURES))
    for i, group in enumerate(groups):
        predictors[i] = (group_assignments == group)

    # Design matrix of the restricted design (no group information)
    restricted_predictors = numpy.ones(shape=(1,N_MEASURES))

    fit = sm.OLS(data.T, predictors.T, missing='drop').fit()
    restricted_fit = sm.OLS(data.T, restricted_predictors.T, missing='drop').fit()

    def compare_f_test(fit, restricted):
        # Work-around for statsmodels issue when the endog matrix is 2d
        def ssr(fit):
            return numpy.sum(fit.wresid * fit.wresid, axis=0)
        ssr_full = ssr(fit)
        ssr_restr = ssr(restricted)
        df_full = fit.df_resid
        df_restr = restricted.df_resid

        df_diff = (df_restr - df_full)
        f_value = (ssr_restr - ssr_full) / df_diff / ssr_full * df_full
        p_value = scipy.stats.f.sf(f_value, df_diff, df_full)
        return f_value, p_value, df_diff
    f,ps,df = compare_f_test(fit, restricted_fit)

    return ps