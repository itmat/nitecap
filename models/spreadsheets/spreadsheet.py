import datetime
from parser import ParserError
from pathlib import Path

import pandas as pd
import numpy
import re
import constants

from sqlalchemy import orm

from db import db
from exceptions import NitecapException
from models.users.user import User
from collections import OrderedDict

import nitecap

NITECAP_DATA_COLUMNS = ["amplitude", "total_delta", "nitecap_q", "peak_time", "trough_time", "nitecap_p", "anova_p"]

class Spreadsheet(db.Model):
    __tablename__ = "spreadsheets"
    id = db.Column(db.Integer, primary_key=True)
    descriptive_name = db.Column(db.String(250), nullable=False)
    days = db.Column(db.Integer, nullable=False)
    timepoints = db.Column(db.Integer, nullable=False)
    repeated_measures = db.Column(db.Boolean, nullable=False, default=False)
    header_row = db.Column(db.Integer, nullable=False, default=1)
    original_filename = db.Column(db.String(250), nullable=False)
    file_mime_type = db.Column(db.String(250), nullable=False)
    breakpoint = db.Column(db.Integer, default=0)
    file_path = db.Column(db.String(250))
    uploaded_file_path = db.Column(db.String(250), nullable=False)
    date_uploaded = db.Column(db.DateTime, nullable=False)
    num_replicates_str = db.Column(db.String(250))
    column_labels_str = db.Column(db.String(2500))
    max_value_filter = db.Column(db.FLOAT)
    last_access = db.Column(db.DateTime, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    user = db.relationship("User")

    def __init__(self, descriptive_name, days, timepoints, repeated_measures, header_row, original_filename,
                 file_mime_type, uploaded_file_path, file_path=None, column_labels_str=None,
                 breakpoint=None, num_replicates_str=None, max_value_filter=None, last_access=None, user_id=None,
                 date_uploaded=None):
        self.descriptive_name = descriptive_name
        self.days = int(days)
        self.timepoints = int(timepoints)
        self.repeated_measures = repeated_measures
        self.header_row = int(header_row)
        self.original_filename = original_filename
        self.file_mime_type = file_mime_type
        self.file_path = file_path
        self.uploaded_file_path = uploaded_file_path
        self.date_uploaded = date_uploaded
        self.num_replicates_str = num_replicates_str
        self.column_labels_str = column_labels_str
        self.max_value_filter = max_value_filter
        self.breakpoint = breakpoint
        self.last_access = last_access if last_access else datetime.datetime.now()
        annonymous_user = User.find_by_username('annonymous')
        if not annonymous_user:
            annonymous_user = User.create_annonymous_user()
        self.user_id = user_id if user_id else annonymous_user.id

        # This is a new spreadsheet.
        if file_path is None:
            self.set_df()
            self.date_uploaded = datetime.datetime.now()
            self.file_path = uploaded_file_path + ".working.txt"
            self.update_dataframe()

        # Do we ever get here?
        else:
            self.df = pd.read_csv(self.file_path, sep="\t")

    @orm.reconstructor
    def init_on_load(self):
        self.error = False
        try:
            if self.file_path:
                self.df = pd.read_csv(self.file_path, sep="\t")
        except Exception as e:
            # The parser failed...we may be able to recover.
            print(e)
            self.df = None
            try:
                self.set_df()

            # If parsing the original fails, we are stuck
            except Exception as e:
                print(e)
                self.error = True

        self.num_replicates = None if not self.num_replicates_str \
            else [int(num_rep) for num_rep in self.num_replicates_str.split(",")]
        self.column_labels = None if not self.column_labels_str else self.column_labels_str.split(",")
        if self.column_labels_str:
            self.identify_columns(self.column_labels)

            if any(column not in self.df.columns for column in NITECAP_DATA_COLUMNS):
                # Run our statistics if we have selected the column labels and are
                # missing any output (eg: if we added more outputs, this will update spreadsheets,
                # or if somehow a spreadsheet was never computed)
                self.compute_nitecap()


    def set_df(self):
        """
        Use the uploaded file's mimetype to determine whether the file in an Excel spreadsheet or the file's
        extension to determine whether the plain text file in comma or tab delimiated and load the dataframe
        appropriately
        """

        try:
            # Spreadsheet is an Excel file (initial sheet only is used)
            if self.file_mime_type in constants.EXCEL_MIME_TYPES:
                self.df = pd.read_excel(self.uploaded_file_path,
                                        header=self.header_row - 1,
                                        index_col=False)
            else:
                extension = Path(self.original_filename).suffix
                sep="\t"
                if extension in constants.COMMA_DELIMITED_EXTENSIONS:
                    sep=","
                self.df = pd.read_csv(self.uploaded_file_path,
                                      sep=sep,
                                      header=self.header_row - 1,
                                      index_col=False)
        except (UnicodeDecodeError, ParserError) as e:
            print(e)
            raise NitecapException("The file provided could not be parsed.")


    def column_defaults(self):
        # Try to guess the columns by looking for CT/ZT labels
        selections = guess_column_labels(self.df.columns, self.timepoints, self.days)
        return list(zip(self.df.columns, selections))


    def identify_columns(self, column_labels):

        # column labels saved as comma delimited string in db
        self.column_labels_str = ",".join(column_labels)
        self.column_labels = column_labels

        x_values = [self.label_to_timepoint(label) for label in self.column_labels]
        self.x_values = [value for value in x_values if value is not None]

        # Count the number of replicates at each timepoint
        self.num_replicates = [len([1 for x in self.x_values if x == i])
                                    for i in range(self.timepoints * self.days)]
        self.num_replicates_str = ",".join([str(num_replicate) for num_replicate in self.num_replicates])


        self.x_values = [i for i,num_reps in enumerate(self.num_replicates)
                            for j in range(num_reps)]
        self.x_labels = [f"Day{i+1} Timepoint{j+1}" for i in range(self.days) for j in range(self.timepoints)]
        self.x_label_values = [i*self.timepoints + j for i in range(self.days) for j in range(self.timepoints)]


        # Also compute all the ways that we can pair adjacent data points, for use in plotting
        # TODO: should this be moved elsewhere? only possible to do after getting column_labels
        self.column_pairs =  []
        first_col_in_timepoint = 0
        for timepoint, num_reps in enumerate(self.num_replicates[:-1]):
            next_num_reps = self.num_replicates[timepoint+1]
            self.column_pairs.extend( [[first_col_in_timepoint + a, first_col_in_timepoint + num_reps + b] for a in range(num_reps)
                                             for b in range(next_num_reps)] )
            first_col_in_timepoint += num_reps

    def get_raw_data(self):
        data_columns = self.get_data_columns()
        return self.df[data_columns]

    def get_data_columns(self):
        # Order the columns by chronological order
        filtered_columns = [(column, label) for column, label in zip(self.df.columns, self.column_labels) if label != 'Ignore']
        ordered_columns = sorted(filtered_columns, key = lambda c_l: self.label_to_daytime(c_l[1]))
        return [column for column, label in ordered_columns]

    def compute_nitecap(self):
        # Runs NITECAP on the data but just to order the features

        data = self.get_raw_data().values
        data_formatted = nitecap.reformat_data(data, self.timepoints, self.num_replicates, self.days)

        # Main nitecap computation
        td, perm_td = nitecap.nitecap_statistics(data_formatted)
        q, p = nitecap.FDR(td, perm_td)

        # Other statistics
        # TODO: should users be able to choose their cycle length?
        amplitude, peak_time, trough_time = nitecap.descriptive_statistics(data_formatted, cycle_length=self.timepoints)
        try:
            anova_p = nitecap.util.anova(data_formatted)
        except ValueError:
            anova_p = numpy.full(shape=data_formatted.shape[2], fill_value=float('nan'))

        self.df["amplitude"] = amplitude
        self.df["peak_time"] = peak_time
        self.df["trough_time"] = trough_time
        self.df["total_delta"] = td
        self.df["anova_p"] = anova_p
        self.df["nitecap_p"] = p
        self.df["nitecap_q"] = q
        self.df = self.df.sort_values(by="total_delta")
        self.update_dataframe()

    def update_dataframe(self):
        self.df.to_csv(self.file_path, sep="\t", index=False)

    def reduce_dataframe(self, breakpoint):
        above_breakpoint = self.df.iloc[:breakpoint+1]
        sorted_by_peak_time = above_breakpoint.sort_values(by="peak_time")
        raw_data = sorted_by_peak_time[self.get_data_columns()]
        labels = list(sorted_by_peak_time.iloc[:,0])
        return raw_data, labels

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
            "user_id": self.user_id,
            "date_uploaded": self.date_uploaded
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
        date_uploaded = data['date_uploaded']
        return cls(days, timepoints, original_filename, uploaded_file_path, file_path, column_labels, breakpoint, num_replicates, user_id)

    def save_to_db(self):
        self.last_access = datetime.datetime.now()
        db.session.add(self)
        db.session.commit()

    def delete_from_db(self):
        db.session.delete(self)
        db.session.commit()

    @classmethod
    def find_by_id(cls, _id):
        return cls.query.filter_by(id=_id).first()

    def update_user(self, user_id):
        self.user_id = user_id
        self.save_to_db()

    def owned(self):
        return not self.user.is_annoymous_user()

column_label_formats = [re.compile("CT(\d+)"), re.compile("ct(\d)"),
                        re.compile("(\d+)CT"), re.compile("(\d)ct"),
                        re.compile("ZT(\d+)"), re.compile("zt(\d+)"),
                        re.compile("(\d+)ZT"), re.compile("(\d+)zt")]

def guess_column_labels(columns, timepoints, days):
    best_num_matches = 0
    best_matches = []
    for fmt in column_label_formats:
        matches = [fmt.search(label) for label in columns]
        num_matches = len([match for match in matches if match])
        if num_matches > best_num_matches:
            best_num_matches = num_matches
            best_matches = matches

    if best_num_matches > 0:
        times = [int(match.groups()[0]) if match else None
                     for match in best_matches]
        selected_columns = [column if match else None
                                 for column, match in zip(columns, best_matches)]
        min_time = min(time for time in times if time is not None)
        max_time = max(time for time in times if time is not None)
        total_time_delta = max_time - min_time
        time_per_timepoint = total_time_delta / (timepoints * days - 1)
        time_point_counts = [(time - min_time)/ time_per_timepoint if match else None
                                for time,match in zip(times,best_matches)]
        if all(int(time_point_count) == time_point_count for time_point_count in time_point_counts if time_point_count is not None):

            selections = [f"Day{int(time_point_count // timepoints)+1} Timepoint{int(time_point_count % timepoints)+1}" if time_point_count is not None else "Ignore"
                            for time_point_count in time_point_counts]
            return selections
        
        # Okay, so the timepoitns aren't evenly distributed
        # But let's check there might be the right number of them
        # assuming that there are constant number of reps per day
        # and that they are in the right order
        if best_num_matches % (timepoints*days) == 0:
            num_reps = int(best_num_matches // timepoints*days)

            selections = []
            selected_below = 0
            for i,column in enumerate(columns):
                if best_matches[i]:
                    day = int(selected_below // timepoints)
                    time = int(selected_below % timepoints)
                    selections.append(f"Day{day+1} Timepoint{time+1}")
                    selected_below += 1
                else:
                    selections.append("Ignore")
            return selections
        return ["Ignore"]*len(columns) # No selections, we have uneven timepoints
    else:
        return ["Ignore"]*len(columns)
