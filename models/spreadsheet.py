import pandas as pd

class Spreadsheet:

    def __init__(self, days, timepoints, file_path, column_labels=None):
        self.days = int(days)
        self.timepoints = int(timepoints)
        self.file_path = file_path
        self.df = pd.read_csv(self.file_path, sep="\t")
        mini_df = self.df[:10]
        self.sample = mini_df.values.tolist()
        self.columns = self.df.columns.values.tolist()
        self.column_labels = column_labels
        self.selections = ['Ignore'] + [f"Day{day + 1} Timepoint{timepoint + 1}"
                      for day in range(self.days) for timepoint in range(self.timepoints)]

        # Try to guess the columns by looking for CT/ZT labels
        default_selections = ['Ignore'] * len(self.df.columns)
        CT_columns = [column for column in self.df.columns if "CT" in column or "ct" in column]
        ZT_columns = [column for column in self.df.columns if "ZT" in column or "zt" in column]

        if len(ZT_columns) > 0 and len(ZT_columns) % (self.days*self.timepoints) == 0:
            # Guess we are using ZT
            num_reps = len(ZT_columns) // (self.days*self.timepoints)
            ZT_selections = [self.selections[1+i] for i in range(self.days*self.timepoints) for _ in range(num_reps)]
            default_selections = ['Ignore' if column not in ZT_columns else ZT_selections[ZT_columns.index(column)]
                                    for column in self.df.columns]

        if len(CT_columns) > 0 and len(CT_columns) % (self.days*self.timepoints) == 0 and len(CT_columns) > len(ZT_columns):
            # Guess we are using CT
            num_reps = len(CT_columns) // (self.days*self.timepoints)
            CT_selections = [self.selections[1+i] for i in range(self.days*self.timepoints) for _ in range(num_reps)]
            default_selections = ['Ignore' if column not in CT_columns else CT_selections[CT_columns.index(column)]
                                    for column in self.df.columns]

        self.column_defaults = list(zip(self.columns, default_selections))


    def identify_columns(self, column_labels):
        self.column_labels = column_labels
        self.x_values = [(index, value) for index, value in enumerate(self.column_labels) if value != 'Ignore']
        x_indices = list(list(zip(*self.x_values))[0])
        self.trimmed_df = self.df.iloc[:, [j for j, _ in enumerate(self.df.columns) if j in x_indices]]


    def to_json(self):
        return {
            "days": self.days,
            "timepoints": self.timepoints,
            "file_path": self.file_path,
            "columns": self.columns,
            "column_labels": self.column_labels
        }

    @classmethod
    def from_json(cls, data):
        days = data['days']
        timepoints = data['timepoints']
        file_path = data['file_path']
        column_labels = data['column_labels']
        return cls(days, timepoints, file_path, column_labels)


