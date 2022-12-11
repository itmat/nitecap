import numpy
import pandas

import statsmodels.api as sm


def perform_two_way_anova(groups_A, data_A, groups_B, data_B):
    '''
    Perform two-way ANOVA between two conditions, A and B

    `groups_A` is a list of integers indicating group membership of each column of data_A
    `data_A` is a numpy array of shape (num_features, num_samples)
            containing the values of the condition A
    `groups_B` is a list of integers indicating group membership of each column of data_B
    `data_B` is a numpy array of shape (num_features, num_samples)
            containing the values of the condition B

    Returns:
    `interaction_p_value` - array length num_features containing p-values for the time-and-dataset interaction
    `main_effect_p_value` - array length num_features containing p-values for the difference between datasets
    '''

    assert len(groups_A) == data_A.shape[1]
    assert len(groups_B) == data_B.shape[1]
    assert data_A.shape[0] == data_B.shape[0]

    # Condition variables for the concatenated datasets
    group_cats = pandas.Series(numpy.concatenate((groups_A, groups_B)), dtype="category")
    groups = pandas.get_dummies(group_cats).values.T
    dataset = [0 for _ in groups_A] + [1 for _ in groups_B]
    interaction = numpy.array(dataset)*groups

    # Run three models, one is the full interaction time-and-dataset model
    # the restricted model has no interaction between time and dataset
    # and the base model is just time
    # comparing full to restricted gives the interaction p-value
    # comparing restricted to base gives the main-effect p-value between the two datasets
    full_model = numpy.vstack( (groups, interaction) )

    # Restriction matrices
    interaction_restrictions = numpy.hstack((
        numpy.zeros((len(interaction)-1, len(groups))),
        # matrix giving successive differences, so all interaction terms are equal, like:
        # 1 -1  0
        # 0  1 -1
        (numpy.identity(len(interaction)) - numpy.diag( numpy.ones(len(interaction)-1), 1))[:-1,:], 
    ))
    main_effect_restriction = numpy.hstack((
        numpy.zeros((1, len(groups))),
        numpy.ones((1, len(interaction))), # Average of all the interaction terms
    ))

    combined_datasets = numpy.concatenate((data_A, data_B), axis=1)

    # Fit models and compute p-values for each gene
    interaction_p_values = numpy.empty(combined_datasets.shape[0])
    main_effect_p_values = numpy.empty(combined_datasets.shape[0])
    for i in range(combined_datasets.shape[0]):
        if numpy.isnan(combined_datasets[i]).all():
            interaction_p_values[i] = float("NaN")
            main_effect_p_values[i] = float("NaN")
            continue
        full_fit = sm.OLS(combined_datasets[i], full_model.T, missing='drop').fit()

        restricted_test = full_fit.f_test(interaction_restrictions)
        interaction_p_values[i] = restricted_test.pvalue

        main_effect_test = full_fit.f_test(main_effect_restriction)
        main_effect_p_values[i] = main_effect_test.pvalue

    return interaction_p_values[0], main_effect_p_values[0]


def two_way_anova(data, sample_collection_times, cycle_length=24):

    groups = []

    for collection_times in sample_collection_times:
        timepoints = sorted(set(collection_times))
        Δt = float(timepoints[1] - timepoints[0])

        groups.append(numpy.round((collection_times % cycle_length) / Δt).astype(int))

    p_interaction = []
    p_main_effect = []

    for data_A, data_B in data:
        interaction_p_value, main_effect_p_value = perform_two_way_anova(
            groups[0], numpy.array([data_A]), groups[1], numpy.array([data_B])
        )

        p_interaction.append(interaction_p_value)
        p_main_effect.append(main_effect_p_value)

    return p_interaction, p_main_effect
