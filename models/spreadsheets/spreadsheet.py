import collections
import datetime
import os
import uuid
import subprocess
from pandas.errors import ParserError
from pathlib import Path
import re

import pandas as pd
import numpy
import pyarrow
import pyarrow.parquet
import constants

from sqlalchemy import orm

from db import db
from exceptions import NitecapException
from models.users.user import User
from flask import current_app
from shutil import copyfile
import copy

import nitecap
from timer_decorator import timeit

NITECAP_DATA_COLUMNS = ["amplitude", "total_delta", "nitecap_q", "peak_time", "trough_time", "nitecap_p", "anova_p", "anova_q"]


class Spreadsheet(db.Model):
    __tablename__ = "spreadsheets"
    id = db.Column(db.Integer, primary_key=True)
    descriptive_name = db.Column(db.String(250), nullable=False)
    days = db.Column(db.Integer)
    timepoints = db.Column(db.Integer)
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
    ids_unique = db.Column(db.Boolean, nullable=False, default=0)
    note = db.Column(db.String(5000))
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    user = db.relationship("User")

    ID_COLUMN = "ID"
    IGNORE_COLUMN = "Ignore"
    NON_DATA_COLUMNS = [ID_COLUMN, IGNORE_COLUMN]

    @timeit
    def __init__(self, descriptive_name, days, timepoints, repeated_measures, header_row, original_filename,
                 file_mime_type, uploaded_file_path, file_path=None, column_labels_str=None,
                 breakpoint=None, num_replicates_str=None, max_value_filter=None, last_access=None, user_id=None,
                 date_uploaded=None, ids_unique=False):
        """
        This method runs only when a Spreadsheet is instantiated for the first time.  SQLAlchemy does not employ this
        method (only __new__).  Many of the parameters are filled in only after the spreadsheet has been instantiated
        and since this method is never used by SQLAlchemy, it may not be necessary to have such a lengthy parameter
        list.
        :param descriptive_name: A name of 250 characters or less describing the spreadsheet content so that the user
        may easily recognize it or search for it in his/her spreadsheet list.
        :param days: The number of days over which the data is collected.
        :param timepoints: The number of timepoints per day over whcih the data is collected.
        :param repeated_measures:
        :param header_row: The how (indexed from 1) where the header info is found (should be a single row)
        :param original_filename: The name of the file originally uploaded.
        :param file_mime_type: The file's mime type (used to distinguish Excel spreadsheets from plain text files)
        :param uploaded_file_path: Where the uploaded file resides on the server (the filename is a uuid here to avoid
        any possible name collisions.)
        :param file_path: Where the file containing the processed version of the spreadsheet resides on the server
        (note that this file is a tab delimited plain text file with the extension working.txt
        :param column_labels_str: A comma delimited listing of the column labels used to identify timepoint and id
        columns.
        :param breakpoint: The cutoff value used to limit the number of rows displayed on a heatmap
        :param num_replicates_str: A comma delimited listing of the number of replicates identified for each timepoint.
        :param max_value_filter: A value below which rows having smaller maximum values are filter out.
        :param last_access: A timestamp indicating when the spreadsheet was last accessed (actually last updated)
        :param user_id: The id of the spreadsheet's owner.  Visitors have individual (although more transitory)
        accounts and consequently a user id.
        :param date_uploaded:  The timestamp at which the original spreadsheet was uploaded.
        :param ids_unique:  Flag indicating whether the ids are unique given the columns selected as ids
        """
        current_app.logger.info('Setting up spreadsheet object')
        self.descriptive_name = descriptive_name
        self.days = days
        self.timepoints = timepoints
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
        self.last_access = last_access if last_access else datetime.datetime.utcnow()
        self.ids_unique = ids_unique
        self.note = ''
        self.user_id = user_id

        # TODO This is a new spreadsheet.  I think the file_path will always be None.
        if file_path is None:
            self.set_df()
            self.date_uploaded = datetime.datetime.utcnow()
            self.file_path = uploaded_file_path + ".working.parquet"
            self.update_dataframe()

        # TODO Do we ever get here?
        else:
            if self.file_path.endswith("txt"):
                self.df = pd.read_csv(self.file_path, sep='\t')
            else:
                self.df = pyarrow.parquet.read_pandas(self.file_path).to_pandas()


    @timeit
    def init_on_load(self):
        """
        The method that runs when SQLAlchemy reloads a Spreadsheet.  A pandas dataframe is rebuilt from the file
        holding processed version of the spreadsheet.  The number of replicates and the column labels are
        re-populated from delimited database strings and nitecap is re-computed if needed.

        Note that there is a provision for handling the instance where the file holding the processed spreadsheet is
        not successfully parsed.  There has been an occasion, at corruption of the processed spreadsheet file,
        involving the loss of a carriage return.  Should this happen, we re-parse the originally uploaded spreadsheet
        file and re-create the processed version.  If the originally uploaded spreadsheet is compromised, we note
        the error without bubbling up the exception.  This method is generally run when a user visits the page
        containing his/her spreadsheets.  We don't want one compromised spreadsheet to impair the user's ability
        to work with other spreadsheets.
        """
        self.error = False
        try:
            if self.file_path:
                if self.file_path.endswith("txt"):
                    self.df = pd.read_csv(self.file_path, sep='\t')
                else:
                    self.df = pyarrow.parquet.read_pandas(self.file_path).to_pandas()
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


        if self.df is not None and ("filtered_out" not in self.df.columns):
            # Everything defaults to unfiltered
            self.df["filtered_out"] = False

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

    @timeit
    def set_df(self):
        """
        Use the uploaded file's mimetype to determine whether the file in an Excel spreadsheet or the file's
        extension to determine whether the plain text file in comma or tab delimiated and load the dataframe
        appropriately.
        """

        try:
            # Spreadsheet is an Excel file (initial sheet only is used)
            if self.file_mime_type in constants.EXCEL_MIME_TYPES:
                self.df = pd.read_excel(self.uploaded_file_path,
                                        header=self.header_row - 1,
                                        index_col=False)
            else:
                extension = Path(self.original_filename).suffix
                sep = "\t"
                if extension.lower() in constants.COMMA_DELIMITED_EXTENSIONS:
                    sep = ","
                self.df = pd.read_csv(self.uploaded_file_path,
                                      sep=sep,
                                      header=self.header_row - 1,
                                      index_col=False)
        except (UnicodeDecodeError, ParserError) as e:
            print(e)
            raise NitecapException("The file provided could not be parsed.")

    def column_defaults(self):
        """
        Try to guess the columns by looking for CT/ZT labels only if days and timepoints are populated.
        :return: a list of tuples having header and guess or ignore column depending on whether days and
        timepoints are set.
        """
        if not self.days or not self.timepoints:
            return list(zip(self.df.columns, Spreadsheet.IGNORE_COLUMN * len(self.df.columns)))
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
            self.column_pairs.extend( [[first_col_in_timepoint + a, first_col_in_timepoint + num_reps + b]
                                       for a in range(num_reps)
                                       for b in range(next_num_reps)] )
            first_col_in_timepoint += num_reps

    def get_raw_data(self):
        data_columns = self.get_data_columns()
        return self.df[data_columns]

    def get_data_columns(self):
        # Order the columns by chronological order
        filtered_columns = [(column, label) for column, label in zip(self.df.columns, self.column_labels)
                            if label not in Spreadsheet.NON_DATA_COLUMNS]
        ordered_columns = sorted(filtered_columns, key = lambda c_l: self.label_to_daytime(c_l[1]))
        return [column for column, label in ordered_columns]

    @timeit
    def get_ids(self, *args):
        """
        Find all the columns in the spreadsheet's dataframe noted as id columns and concatenate the contents
        of those columns into a numpy series
        :return: a numpy series containing the complete id for each data row.
        """
        if not args:
            id_indices = [index
                          for index, column_label in enumerate(self.column_labels)
                          if column_label == Spreadsheet.ID_COLUMN]
        else:
            id_indices = args[0]

        if len(id_indices) == 1:
            return self.df.iloc[:,id_indices[0]].astype(str).tolist()

        # Concatenate the id columns using pandas.Series.str.cat() function
        # convert to type string first since otherwise blank entries will result in float('NaN')
        first_id = id_indices[0]
        concats = self.df.iloc[:,first_id].astype(str).str.cat(self.df.iloc[:,id_indices[1:]].astype(str), ' | ')
        return concats.tolist()

    def find_replicate_ids(self, *args):
        ids = list(self.get_ids(*args))
        return [item for item, count in collections.Counter(ids).items() if count > 1]

    def find_unique_ids(self):
        ids = list(self.get_ids())
        return [item for item, count in collections.Counter(ids).items() if count == 1]

    def set_ids_unique(self):
        """
        Determines whether the results of concatenating all ids columns together into a list results in a list of
        unique ids.  Sets a flag in the spreadsheet accordingly (which will be added to the db)
        """
        ids = self.get_ids()
        self.ids_unique = len(ids) == len(set(ids))

    @timeit
    def compute_nitecap(self):
        # Runs NITECAP on the data but just to order the features

        data = self.get_raw_data().values
        filtered_out = self.df.filtered_out.values.astype("bool") # Ensure bool and not 0,1, should be unnecessary
        data_formatted = nitecap.reformat_data(data, self.timepoints, self.num_replicates, self.days)

        # Seed the computation so that results are reproducible
        numpy.random.seed(1)

        # Main nitecap computation
        td, perm_td = nitecap.nitecap_statistics(data_formatted, num_cycles=self.days)

        # Apply q-value computation but just for the features surviving filtering
        good_td, good_perm_td = td[~filtered_out], perm_td[:,~filtered_out]
        good_q, good_p = nitecap.FDR(good_td, good_perm_td)

        q = numpy.empty(td.shape)
        q[~filtered_out] = good_q
        q[filtered_out] = float("NaN")

        p = numpy.empty(td.shape)
        p[~filtered_out] = good_p
        p[filtered_out] = float("NaN")

        self.df["nitecap_p"] = p
        self.df["nitecap_q"] = q

        # Other statistics
        # TODO: should users be able to choose their cycle length?
        amplitude, peak_time, trough_time = nitecap.descriptive_statistics(data_formatted, num_cycles = self.days, cycle_length=self.timepoints)
        try:
            anova_p = nitecap.util.anova(data_formatted)
            anova_q = nitecap.util.BH_FDR(anova_p)
        except ValueError:
            # Can't run anova (eg: no replicates)
            anova_p = numpy.full(shape=data_formatted.shape[2], fill_value=float('nan'))
            anova_q = numpy.full(shape=data_formatted.shape[2], fill_value=float('nan'))

        self.df["amplitude"] = amplitude
        self.df["peak_time"] = peak_time
        self.df["trough_time"] = trough_time
        self.df["total_delta"] = td
        self.df["anova_p"] = anova_p
        self.df["anova_q"] = anova_q
        self.df = self.df.sort_values(by="total_delta")
        self.update_dataframe()

    @timeit
    def update_dataframe(self):
        if self.file_path.endswith("txt"):
            self.df.to_csv(self.file_path, sep="\t", index=False)
        else:
            # in order to write out, we always need our non-numeric columns to be type string
            # otherwise parquet gives unpredictable results and errors
            str_columns = [col for col,typ in self.df.dtypes.items() if typ == object]
            df = self.df.astype({col: 'str' for col in str_columns})
            pyarrow.parquet.write_table(pyarrow.Table.from_pandas(df, preserve_index=False), self.file_path)

    def reduce_dataframe(self, breakpoint):
        above_breakpoint = self.df.iloc[:breakpoint+1]
        sorted_by_peak_time = above_breakpoint.sort_values(by="peak_time")
        raw_data = sorted_by_peak_time[self.get_data_columns()]
        id_indices = [index for index, column_label in enumerate(self.column_labels)
                                if column_label == Spreadsheet.ID_COLUMN]
        labels = list(sorted_by_peak_time.iloc[:,id_indices].apply(lambda row: ' | '.join([str(ID) for ID in row]), axis=1))

        original_indexes = numpy.argsort(above_breakpoint.peak_time)

        return raw_data, labels, original_indexes

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

    @timeit
    def get_jtk(self):
        if "jtk_p" not in self.df.columns or "jtk_q" not in self.df.columns:
            # Call out to an R script to run JTK
            # write results to disk to pass the data to JTK
            run_jtk_file = os.path.normpath(os.path.join(os.path.dirname(__file__), "../../run_jtk.R"))
            jtk_source_file = os.path.normpath(os.path.join(os.path.dirname(__file__), "../../JTK_CYCLEv3.1.R"))
            data_file_path = f"/tmp/{uuid.uuid4()}"
            self.get_raw_data().to_csv(data_file_path, sep="\t", index=False)
            results_file_path = f"{data_file_path}.jtk_results"

            # TODO: what value should we give here?
            # probably doesn't matter if we aren't reporting JTK phase
            hours_between_timepoints = 1
            num_reps = ','.join(str(x) for x in self.num_replicates)

            res = subprocess.run(f"Rscript {run_jtk_file} {jtk_source_file} {data_file_path} {results_file_path} {self.timepoints} {num_reps} {self.days} {hours_between_timepoints}",
                                    shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            if res.returncode != 0:
                raise RuntimeError(f"Error running JTK: \n {res.argsedecode('ascii')} \n {res.stdout.decode('ascii')} \n {res.stderr.decode('ascii')}")

            results = pd.read_table(results_file_path)
            self.df["jtk_p"] = results.JTK_P
            self.df["jtk_q"] = results.JTK_Q

            self.update_dataframe()

            os.remove(data_file_path)
            os.remove(results_file_path)
        return self.df.jtk_p.tolist(), self.df.jtk_q.tolist()

    def clear_jtk(self):
        ''' Clear JTK computations so that it will be recomputed

        For example if the spreadsheet days/timepoints changed '''

        if "jtk_p" in self.df.columns:
            self.df.drop(columns="jtk_p", inplace=True)
        if "jtk_q" in self.df.columns:
            self.df.drop(columns="jtk_q", inplace=True)
        self.update_dataframe()

    @staticmethod
    def normalize_data(raw_data):
        means = raw_data.mean(axis=1)
        stds = raw_data.std(axis=1)
        return raw_data.sub(means, axis=0).div(stds, axis=0)

    def average_replicates(self, data):
        avg = numpy.empty((data.shape[0], self.days*self.timepoints))
        x_values = numpy.array(self.x_values)
        for i in range(self.days*self.timepoints):
            avg[:,i] = numpy.sum(data.values[:, x_values == i], axis=1)
            avg[:,i] /= numpy.sum(x_values == i)
        return pd.DataFrame(avg)

    def validate(self, column_labels):
        """ Check spreadhseet for consistency.

        In particular, need the column identifies to match what NITECAP can support.
        Every timepoint must have the same number of columns and every day must have all of its timepoints"""

        errors = []

        if Spreadsheet.ID_COLUMN not in column_labels:
            errors.append(f"There should be at least one ID column.")

        retained_columns = [column for column, label in zip(self.df.columns, column_labels) if label != 'Ignore']
        type_pattern = re.compile(r"^([a-zA-Z]+)\d*$")
        for retained_column in retained_columns:
            type_match = re.match(type_pattern, str(self.df[retained_column].dtype))
            if not Spreadsheet.ID_COLUMN and (not type_match or type_match.group(1) not in ['int', 'uint', 'float']):
                errors.append(f"Column '{retained_column}' must contain only numerical data to be employed as a timepoint.")

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
                errors.append(f"Day {i + 1} does not have data for all timepoints."
                                f" Missing timepoint {', '.join(str(time) for time in missing)}")
        return errors

    def get_sample_dataframe(self):
        mini_df = self.df[:10]
        return mini_df.values.tolist()

    def get_selection_options(self):

        # If days or timepoints are not set, just provide an ignore column option.
        if not self.days or not self.timepoints:
            return [Spreadsheet.IGNORE_COLUMN]

        return ['Ignore'] + ['ID'] + [f"Day{day + 1} Timepoint{timepoint + 1}"
                                    for day in range(self.days)
                                    for timepoint in range(self.timepoints)]


    def label_to_daytime(self, label):
        """ returns the day and time of column label """
        match = re.search("Day(\d+) Timepoint(\d+)", label)
        if match:
            d, t = match.groups()
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

    def get_total_diskspace_used(self):
        """
        Get the total size in MB of the disk space consumed by the original spreadsheet file and
        its processed equivalent.
        :return: total used diskspace in MB of this spreadsheet object.
        """
        return round((os.path.getsize(self.uploaded_file_path) + os.path.getsize(self.file_path))/1E6,3)

    @timeit
    def save_to_db(self):
        """
        Save the spreadsheet to the database and note the current time as the last modified time in the
        database.
        """
        self.last_access = datetime.datetime.utcnow()
        db.session.add(self)
        db.session.commit()

    def delete_from_db(self):
        """
        Remove this spreadsheet from the database
        """
        db.session.delete(self)
        db.session.commit()

    @classmethod
    def find_by_id(cls, _id):
        """
        Find the spreadsheet identified by the given id.
        :param _id: The spreadsheet id provided
        :return: The spreadsheet, if found....otherwise None
        """
        return cls.query.filter_by(id=_id).first()

    def update_user(self, user_id):
        """
        Change ownership of this spreadsheet to the user identified by the given id.  This happens when
        a visitor who has been working on one or more spreadsheets, decides to log in.  This spreadsheets should have
        previously been owned visitor account.
        :param user_id: id of new owner of this spreadsheet
        """
        self.user_id = user_id
        self.save_to_db()

    def delete(self):
        """
        Deletes this spreadsheet by removing it from the spreadsheets database table and removing its
        file footprint.
        :return: an error message or None in the case of no error
        """
        error = None
        error_message = f"The data for spreadsheet {self.id} could not all be successfully expunged."
        try:
            self.delete_from_db()
            os.remove(self.file_path)
            os.remove(self.uploaded_file_path)
        except Exception as e:
            current_app.logger.error(error_message, e)
            error = error_message
        return error

    def apply_filters(self):
        self.df["filtered_out"] = False

        if self.max_value_filter is not None:
            maxes = self.get_raw_data().max(axis=1)
            self.df["filtered_out"] = numpy.logical_or(self.df["filtered_out"],  maxes <= self.max_value_filter)

        # Must recalculate q-values on the filtered part
        # TODO: ideally we wouldn't have to recompute all of this
        #       only really want to recompute the q-values but then
        #       we need the permutation values too and we don't store that
        # TODO: this code is copy-and-pasted from compute_nitecap(), shouldn't be duplicated
        data = self.get_raw_data().values
        filtered_out = self.df.filtered_out.values.astype("bool") #Ensure bool and not 0,1, should be unnecessary
        data_formatted = nitecap.reformat_data(data, self.timepoints, self.num_replicates, self.days)

        # Seed the computation so that results are reproducible
        numpy.random.seed(1)

        # Main nitecap computation
        td, perm_td = nitecap.nitecap_statistics(data_formatted, num_cycles=self.days)

        # Apply q-value computation but just for the features surviving filtering
        good_td, good_perm_td = td[~filtered_out], perm_td[:,~filtered_out]
        good_q, good_p = nitecap.FDR(good_td, good_perm_td)

        q = numpy.empty(td.shape)
        q[~filtered_out] = good_q
        q[filtered_out] = float("NaN")

        p = numpy.empty(td.shape)
        p[~filtered_out] = good_p
        p[filtered_out] = float("NaN")

        self.df["nitecap_p"] = p
        self.df["nitecap_q"] = q

        self.update_dataframe()

    @staticmethod
    def make_share_copy(spreadsheet, user_id):
        extension = Path(spreadsheet.original_filename).suffix
        share_filename = uuid.uuid4().hex + extension
        share_file_path = os.path.join(os.environ.get('UPLOAD_FOLDER'), share_filename)
        copyfile(spreadsheet.uploaded_file_path, share_file_path)
        if spreadsheet.file_path.endswith("txt"):
            share_processed_file_path = share_file_path + ".working.txt"
        else:
            share_processed_file_path = share_file_path + ".working.parquet"
        copyfile(spreadsheet.file_path, share_processed_file_path)
        spreadsheet_share = Spreadsheet(descriptive_name=spreadsheet.descriptive_name,
                                  days=spreadsheet.days,
                                  timepoints=spreadsheet.timepoints,
                                  repeated_measures=spreadsheet.repeated_measures,
                                  header_row=spreadsheet.header_row,
                                  original_filename=share_filename,
                                  file_mime_type=spreadsheet.file_mime_type,
                                  uploaded_file_path=share_file_path,
                                  date_uploaded=datetime.datetime.utcnow(),
                                  file_path=share_processed_file_path,
                                  column_labels_str=spreadsheet.column_labels_str,
                                  breakpoint=spreadsheet.breakpoint,
                                  num_replicates_str=spreadsheet.num_replicates_str,
                                  max_value_filter=spreadsheet.max_value_filter,
                                  last_access=None,
                                  user_id=user_id)
        spreadsheet_share.save_to_db()
        return spreadsheet_share

    def get_timepoint_labels(self):
        return set(filter(lambda column_label:
                      column_label != Spreadsheet.ID_COLUMN and column_label != Spreadsheet.IGNORE_COLUMN,
                      self.column_labels))

    @staticmethod
    def check_for_timepoint_consistency(spreadsheets):
        errors = []
        if not spreadsheets or len(spreadsheets) < 2:
            errors.append("Insufficient spreadsheets were provided for comparisons.")
            return errors
        missing_column_labels = [spreadsheet.descriptive_name for spreadsheet in spreadsheets
                                 if not spreadsheet.column_labels]
        if missing_column_labels:
            errors.append(f'Column labels for the following spreadsheet(s) are not specified: '
                          f'{",".join(missing_column_labels)}.  You may have skipped this step.  Go back and re-edit')
            return errors
        timepoint_labels = spreadsheets[0].get_timepoint_labels()
        for spreadsheet in spreadsheets[1:]:
            other_timepoint_labels = spreadsheet.get_timepoint_labels()
            if timepoint_labels != other_timepoint_labels:
                errors.append("Timepoints must be the same for the comparison of multiple spreadsheets.")
        return errors

column_label_formats = [re.compile(r"CT(\d+)"), re.compile(r"ct(\d)"),
                        re.compile(r"(\d+)CT"), re.compile(r"(\d)ct"),
                        re.compile(r"ZT(\d+)"), re.compile(r"zt(\d+)"),
                        re.compile(r"(\d+)ZT"), re.compile(r"(\d+)zt")]

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
                                for time, match in zip(times,best_matches)]
        if all(int(time_point_count) == time_point_count for time_point_count in time_point_counts if time_point_count is not None):

            selections = [f"Day{int(time_point_count // timepoints)+1} Timepoint{int(time_point_count % timepoints)+1}"
                          if time_point_count is not None else "Ignore"
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
        return ["Ignore"]*len(columns)  # No selections, we have uneven timepoints
    else:
        return ["Ignore"]*len(columns)

