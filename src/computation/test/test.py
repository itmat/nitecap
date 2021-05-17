import sys
import numpy as np
import pandas as pd
import simplejson as json

import rpy2.robjects as R
from rpy2.robjects import pandas2ri

sys.path.append("..")
from algorithms import compute

R.r.library("MetaCycle")
meta2d = R.r["meta2d"]

pandas2ri.activate()

spreadsheets = {}
data_directories = ["6.6.4", "6.24.1", "8.9.2", "8.19.1", "24.48.2"]

for directory in data_directories:
    spreadsheet = {}
    with open(f"data/{directory}/metadata.json") as file:
        spreadsheet["metadata"] = json.load(file)

    number_of_samples = len(spreadsheet["metadata"]["timepoints"])

    spreadsheet["dataframe"] = {
        "python": pd.read_csv(
            f"data/{directory}/spreadsheet.tsv", index_col=0, sep="\t"
        ),
        "R": pandas2ri.py2rpy_pandasdataframe(
            pd.read_csv(f"data/{directory}/spreadsheet.tsv", sep="\t").iloc[
                :, : 1 + number_of_samples
            ]
        ),
    }

    spreadsheet["data"] = spreadsheet["dataframe"]["python"].to_numpy()[
        :, :number_of_samples
    ]

    spreadsheets[directory] = spreadsheet


for data_directory, spreadsheet in spreadsheets.items():
    metadata = spreadsheet["metadata"]

    df = spreadsheet["dataframe"]["python"]

    data = spreadsheet["data"]
    timepoints = np.array(metadata["timepoints"])
    cycle_length = metadata["cycle_length"]

    ARSER, JTK, LS = 0, 1, 2

    print("SPREADSHEET:", data_directory)

    ###### COSINOR ######

    print("COSINOR")

    x, p = compute("cosinor")(data, timepoints, cycle_length)

    df["p"] = p

    print(df[["cosinor_p", "p"]])
    print("Correlation matrix:")
    print(df[["cosinor_p", "p"]].corr())

    ###### ONE WAY ANOVA ######

    print("ONE WAY ANOVA")

    (p,) = compute("one_way_anova")(data, timepoints, cycle_length)

    df["p"] = p

    print(df[["anova_p", "p"]])
    print("Correlation matrix:")
    print(df[["anova_p", "p"]].corr())

    ###### LOMB-SCARGLE ######

    print("LOMB-SCARGLE")

    (p,) = compute("ls")(data, timepoints)

    df["p"] = p

    meta2d_results = meta2d(
        infile="N/A",
        filestyle="txt",
        outputFile=False,
        timepoints=R.FloatVector(timepoints),
        cycMethod="LS",
        inDF=spreadsheet["dataframe"]["R"],
    )

    df["meta2d"] = np.array(meta2d_results[LS]["p"])

    print(df[["ls_p", "meta2d", "p"]])
    print("Correlation matrix:")
    print(df[["ls_p", "meta2d", "p"]].corr())

    ###### JTK ######

    print("JTK")

    (p,) = compute("jtk")(data, timepoints)

    df["p"] = p

    results = meta2d(
        infile="N/A",
        filestyle="txt",
        outputFile=False,
        timepoints=R.FloatVector(timepoints),
        cycMethod="JTK",
        inDF=spreadsheet["dataframe"]["R"],
    )

    df["meta2d"] = np.array(results[JTK]["ADJ.P"])

    print(df[["jtk_p", "meta2d", "p"]])
    print("CORRELATION MATRIX")
    print(df[["jtk_p", "meta2d", "p"]].corr())

    ###### ARSER ######

    print("ARSER")

    try:
        (p,) = compute("arser")(data, timepoints)
    except ValueError as error:
        print(error)
        continue

    df["p"] = p

    print(df[["ars_p", "p"]])
    print("CORRELATION MATRIX")
    print(df[["ars_p", "p"]].corr())
