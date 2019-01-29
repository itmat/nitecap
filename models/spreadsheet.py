import pandas as pd
import re

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
        if column_labels:
            self.identify_columns(column_labels)
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
        #self.x_values = [(index, value) for index, value in enumerate(self.column_labels) if value != 'Ignore']

        x_values = [self.label_to_timepoint(label) for label in self.column_labels]
        self.x_values = [value for value in x_values if value is not None]

        x_indices = [index for index, value in enumerate(self.column_labels) if value != 'Ignore']
        self.trimmed_df = self.df.iloc[:, [j for j, _ in enumerate(self.df.columns) if j in x_indices]]

        # Also compute all the ways that we can pair adjacent data points, for use in plotting
        # TODO: for this, we need to validate that all possible timepoints have at least one datapoint
        # and in fact for nitecap we need to validate that all timepoints have the same number of datapoints
        # TODO: should this be moved elsewhere? only possible to do after getting column_labels
        columns_by_timepoint = dict()
        for column, x_value in enumerate(self.x_values):
            if x_value in columns_by_timepoint:
                columns_by_timepoint[x_value].append(column)
            else:
                columns_by_timepoint[x_value] = [column]
        self.column_pairs =  []
        self.timepoint_pairs = []
        for timepoint in range(max(columns_by_timepoint.keys())):
            next_timepoint = timepoint + 1
            self.column_pairs.extend( [[a,b] for a in columns_by_timepoint[timepoint]
                                            for b in columns_by_timepoint[next_timepoint]] )
            self.timepoint_pairs.extend( [[timepoint, next_timepoint]
                                        for _ in range(len(columns_by_timepoint[timepoint])
                                                        * len(columns_by_timepoint[next_timepoint]))] )

    def validate(self, columns):
        ''' Check spreadhseet for consistency.

        In particular, need the column identifies to match what NITECAP can support.
        Every timepoint must have the same number of columns and every day must have all of its timepoints'''
        if self.columns is None:
            return "No columns selected"

        daytimes = [self.label_to_daytime(column_daytime) for column_daytime in columns]
        daytimes = [daytime for daytime in daytimes if daytime is not None]
        days = [daytime[0] for daytime in daytimes if daytime is not None]
        times_of_day = [daytime[1] for daytime in daytimes if daytime is not None]

        # Check that each day has all the timepoints
        all_times = set(range(1,self.timepoints+1))
        for i in range(self.days):
            times_in_day = set([time for day, time in daytimes if day == i+1])
            if times_in_day != all_times:
                missing = all_times.difference(times_in_day)
                return f"Day {i+1} does not have data for all timepoints. Missing timepoint {', '.join(str(time) for time in missing)}"

        return "okay"

    def to_json(self):
        return {
            "days": self.days,
            "timepoints": self.timepoints,
            "file_path": self.file_path,
            "columns": self.columns,
            "column_labels": self.column_labels
        }

    def label_to_daytime(self, label):
        ''' returns the day and time of column label '''
        match = re.search("Day(\d+) Timepoint(\d+)", label)
        if match:
            d,t = match.groups()
            return int(d), int(t)
        else:
            return None

    def label_to_timepoint(self, label):
        match = self.label_to_daytime(label)
        if match:
            d,t = match
            return (t-1) + (d-1)*self.timepoints
        else:
            return None

    @classmethod
    def from_json(cls, data):
        days = data['days']
        timepoints = data['timepoints']
        file_path = data['file_path']
        column_labels = data['column_labels']
        return cls(days, timepoints, file_path, column_labels)
