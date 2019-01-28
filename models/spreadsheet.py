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


