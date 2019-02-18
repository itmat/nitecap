import datetime

import pandas as pd
import numpy
import re

from db import db
from models.users.user import User
from collections import OrderedDict

import nitecap


class Spreadsheet(db.Model):
    __tablename__ = "spreadsheets"
    id = db.Column(db.Integer, primary_key=True)
    days = db.Column(db.Integer, nullable=False)
    timepoints = db.Column(db.Integer, nullable=False)
    original_filename = db.Column(db.String(250), nullable=False)
    breakpoint = db.Column(db.Integer)
    num_replicates = db.Column(db.Integer)
    file_path = db.Column(db.String(250))
    uploaded_file_path = db.Column(db.String(250), nullable=False)
    date_uploaded = db.Column(db.DateTime, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    user = db.relationship("User")

    def __init__(self, days, timepoints, original_filename,
                 uploaded_file_path, file_path=None, column_labels=None,
                 breakpoint=None, num_replicates=None, user_id=None):
        self.days = int(days)
        self.timepoints = int(timepoints)
        self.original_filename = original_filename
        self.file_path = file_path
        self.uploaded_file_path = uploaded_file_path
        annonymous_user = User.find_by_username('annonymous')
        if not annonymous_user:
            annonymous_user = User.create_annonymous_user()
        print(annonymous_user)
        self.user_id = user_id if user_id else annonymous_user.id
        if file_path is None:
            # Need to use our uploaded_file_path to create a new dataframe
            print("Uploaded " + self.uploaded_file_path)
            uploaded_dataframe = pd.read_csv(self.uploaded_file_path, sep="\t")
            self.date_uploaded = datetime.datetime.now()
            self.file_path = uploaded_file_path + ".working.txt"
            self.df = uploaded_dataframe
            self.update_dataframe()
        else:
            self.df = pd.read_csv(self.file_path, sep="\t")

        self.num_replicates = num_replicates
        self.column_labels = column_labels
        self.breakpoint = breakpoint
        if column_labels:
            self.identify_columns(column_labels)


    def column_defaults(self):
        # Try to guess the columns by looking for CT/ZT labels
        selections = self.get_selection_options()

        default_selections = ['Ignore'] * len(self.df.columns)
        CT_columns = [column for column in self.df.columns if "CT" in column or "ct" in column]
        ZT_columns = [column for column in self.df.columns if "ZT" in column or "zt" in column]

        if len(ZT_columns) > 0 and len(ZT_columns) % (self.days*self.timepoints) == 0:
            # Guess we are using ZT
            num_reps = len(ZT_columns) // (self.days*self.timepoints)
            ZT_selections = [selections[1+i] for i in range(self.days*self.timepoints) for _ in range(num_reps)]
            default_selections = ['Ignore' if column not in ZT_columns else ZT_selections[ZT_columns.index(column)]
                                    for column in self.df.columns]

        if len(CT_columns) > 0 and len(CT_columns) % (self.days*self.timepoints) == 0 and len(CT_columns) > len(ZT_columns):
            # Guess we are using CT
            num_reps = len(CT_columns) // (self.days*self.timepoints)
            CT_selections = [selections[1+i] for i in range(self.days*self.timepoints) for _ in range(num_reps)]
            default_selections = ['Ignore' if column not in CT_columns else CT_selections[CT_columns.index(column)]
                                    for column in self.df.columns]

        return list(zip(self.df.columns, default_selections))


    def identify_columns(self, column_labels):
        self.column_labels = column_labels

        x_values = [self.label_to_timepoint(label) for label in self.column_labels]
        self.x_values = [value for value in x_values if value is not None]

        # Essentially the x coordinate for the basketweave plots.
        self.x_labels = list(OrderedDict({label:None for label in self.column_labels if re.search("Day(\d+) Timepoint(\d+)", label)}).keys())

        x_indices = [index for index, value in enumerate(self.column_labels) if value != 'Ignore']

        columns_by_timepoint = dict()
        for column, x_value in enumerate(self.x_values):
            if x_value in columns_by_timepoint:
                columns_by_timepoint[x_value].append(column)
            else:
                columns_by_timepoint[x_value] = [column]

        # Count the number of replicates at each timepoint
        self.num_replicates = [len(columns_by_timepoint.get(i, [])) for i in range(self.timepoints * self.days)]

        # Also compute all the ways that we can pair adjacent data points, for use in plotting
        # TODO: should this be moved elsewhere? only possible to do after getting column_labels
        self.column_pairs =  []
        self.timepoint_pairs = []
        for timepoint in range(max(columns_by_timepoint.keys())):
            next_timepoint = timepoint + 1
            self.column_pairs.extend( [[a,b] for a in columns_by_timepoint[timepoint]
                                            for b in columns_by_timepoint[next_timepoint]] )
            self.timepoint_pairs.extend( [[timepoint, next_timepoint]
                                        for _ in range(len(columns_by_timepoint[timepoint])
                                                        * len(columns_by_timepoint[next_timepoint]))] )
    def get_raw_data(self):
        data_columns = self.get_data_columns()
        return self.df[data_columns]

    def get_data_columns(self):
        # Order the columns by their timepoint (not their days, so we collect across days)
        filtered_columns = [(column, label) for column, label in zip(self.df.columns, self.column_labels) if label != 'Ignore']
        ordered_columns = sorted(filtered_columns, key = lambda c_l: self.label_to_daytime(c_l[1])[1] )
        return [column for column, label in ordered_columns]

    def compute_ordering(self):
        # Runs NITECAP on the data but just to order the features

        data = self.get_raw_data().values
        data_formatted = nitecap.reformat_data(data, self.timepoints, self.num_replicates, self.days)
        td, perm_td, perm_data = nitecap.nitecap_statistics(data_formatted)

        self.df["total_delta"] = td
        self.df = self.df.sort_values(by="total_delta")
        self.update_dataframe()

    def update_dataframe(self):
        self.df.to_csv(self.file_path, sep="\t", index=False)

    def reduce_dataframe(self, breakpoint):
        raw_data = self.get_raw_data()
        heatmap_df = raw_data.iloc[:breakpoint+1]
        labels = list(self.df.iloc[:breakpoint+1]["id"])
        return heatmap_df, labels

    def check_breakpoint(self, breakpoint):
        error = False
        messages = []
        if not breakpoint.isdigit():
            error = True
            messages = f"The breakpoint must be a valid integer."
        elif breakpoint > len(self.df.index):
            error = True
            messages = f"The breakpoin must point to a row inside the spreadsheet."
        return error, messages




    @staticmethod
    def normalize_data(raw_data):
        #TODO: do we always want to log first?
        raw_data = numpy.log(1 + raw_data)
        means = raw_data.mean(axis=1)
        stds = raw_data.std(axis=1)
        return raw_data.sub(means, axis=0).div(stds, axis=0)

    def validate(self, column_labels):
        ''' Check spreadhseet for consistency.

        In particular, need the column identifies to match what NITECAP can support.
        Every timepoint must have the same number of columns and every day must have all of its timepoints'''

        messages = []
        error = False

        retained_columns = [column for column, label in zip(self.df.columns, column_labels) if label != 'Ignore']
        type_pattern = re.compile(r"^([a-zA-Z]+)\d*$")
        for retained_column in retained_columns:
            type_match = re.match(type_pattern, str(self.df[retained_column].dtype))
            if not type_match or type_match.group(1) not in ['int', 'uint', 'float']:
                error = True
                messages.append(f"Column '{retained_column}' must contain only numerical data to be employed as a timepoint.")


        daytimes = [self.label_to_daytime(column_daytime) for column_daytime in column_labels]
        daytimes = [daytime for daytime in daytimes if daytime is not None]
        days = [daytime[0] for daytime in daytimes if daytime is not None]
        times_of_day = [daytime[1] for daytime in daytimes if daytime is not None]

        # Check that each day has all the timepoints
        all_times = set(range(1, self.timepoints + 1))
        for i in range(self.days):
            times_in_day = set([time for day, time in daytimes if day == i + 1])
            if times_in_day != all_times:
                missing = all_times.difference(times_in_day)
                error = True
                messages.append(f"Day {i + 1} does not have data for all timepoints."
                                f" Missing timepoint {', '.join(str(time) for time in missing)}")
        return (error, messages)


    def get_sample_dataframe(self):
        mini_df = self.df[:10]
        return mini_df.values.tolist()

    def get_selection_options(self):
        return ['Ignore'] + [f"Day{day + 1} Timepoint{timepoint + 1}"
                      for day in range(self.days) for timepoint in range(self.timepoints)]


    def to_json(self):
        return {
            "days": self.days,
            "timepoints": self.timepoints,
            "original_filename": self.original_filename,
            "uploaded_file_path": self.uploaded_file_path,
            "file_path": self.file_path,
            "column_labels": self.column_labels,
            "num_replicates": self.num_replicates,
            "breakpoint": self.breakpoint,
            "user_id": self.user_id
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
        original_filename = data['original_filename']
        uploaded_file_path = data['uploaded_file_path']
        file_path = data['file_path']
        column_labels = data['column_labels']
        num_replicates = data['num_replicates']
        breakpoint = data['breakpoint']
        user_id = data['user_id']
        return cls(days, timepoints, original_filename, uploaded_file_path, file_path, column_labels, breakpoint, num_replicates, user_id)

    def save_to_db(self):
        db.session.add(self)
        db.session.commit()

    def delete_from_db(self):
        db.session.delete(self)
        db.session.commit()
