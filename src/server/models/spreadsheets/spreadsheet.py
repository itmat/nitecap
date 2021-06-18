import collections
import datetime
import itertools
import json
import os
import shutil
import uuid
import subprocess
from pandas.errors import ParserError
from pathlib import Path
import re
from string import Template

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

NITECAP_DATA_COLUMNS = ["amplitude", "total_delta", "nitecap_q", "peak_time", "trough_time", "nitecap_p",]
CATEGORICAL_DATA_COLUMNS = ["anova_p", "anova_q"]
MAX_JTK_COLUMNS = 85

class Spreadsheet(db.Model):
    __tablename__ = "spreadsheets"
    id = db.Column(db.Integer, primary_key=True)
    descriptive_name = db.Column(db.String(250), nullable=False)
    num_timepoints = db.Column(db.Integer)
    timepoints = db.Column(db.Integer)
    repeated_measures = db.Column(db.Boolean, nullable=False, default=False)
    header_row = db.Column(db.Integer, nullable=False, default=1)
    original_filename = db.Column(db.String(250), nullable=False)
    file_mime_type = db.Column(db.String(250), nullable=False)
    file_path = db.Column(db.String(250))
    uploaded_file_path = db.Column(db.String(250), nullable=False)
    date_uploaded = db.Column(db.DateTime, nullable=False)
    column_labels_str = db.Column(db.String(2500))
    last_access = db.Column(db.DateTime, nullable=False)
    ids_unique = db.Column(db.Boolean, nullable=False, default=0) # Deprecated - can't remove without modifying the DB since it is nonnullable
    note = db.Column(db.String(5000))
    spreadsheet_data_path = db.Column(db.String(250))
    categorical_data = db.Column(db.String(5000))
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    user = db.relationship("User")
    edit_version = db.Column(db.Integer, default=0)

    ID_COLUMN = "ID"
    IGNORE_COLUMN = "Ignore"
    STAT_COLUMN = "Stat"
    NON_DATA_COLUMNS = [IGNORE_COLUMN, ID_COLUMN, STAT_COLUMN]
    OPTIONAL_COLUMNS = [IGNORE_COLUMN, STAT_COLUMN]
    UPLOADED_SPREADSHEET_FILE_PART = "uploaded_spreadsheet"
    PROCESSED_SPREADSHEET_FILE_PART = "processed_spreadsheet"
    PROCESSED_SPREADSHEET_FILE_EXT =  "parquet"
    SPREADSHEET_DIRECTORY_NAME_TEMPLATE = Template('spreadsheet_$spreadsheet_id')

    @timeit
    def __init__(self, descriptive_name, num_timepoints, timepoints, repeated_measures, header_row, original_filename,
                 file_mime_type, uploaded_file_path, file_path=None, column_labels_str=None,
                 last_access=None, user_id=None,
                 date_uploaded=None, spreadsheet_data_path='', categorical_data=''):
        """
        This method runs only when a Spreadsheet is instantiated for the first time.  SQLAlchemy does not employ this
        method (only __new__).  Many of the parameters are filled in only after the spreadsheet has been instantiated
        and since this method is never used by SQLAlchemy, it may not be necessary to have such a lengthy parameter
        list.
        :param descriptive_name: A name of 250 characters or less describing the spreadsheet content so that the user
        may easily recognize it or search for it in his/her spreadsheet list.
        :param num_timepoints: The number of timepoints in the spreadsheet (across all the cycles)
        :param timepoints: The number of timepoints per day over whcih the data is collected.
        :param repeated_measures:
        :param header_row: The how (indexed from 1) where the header info is found (should be a single row)
        :param original_filename: The name of the file originally uploaded.
        :param file_mime_type: The file's mime type (used to distinguish Excel spreadsheets from plain text files)
        :param uploaded_file_path: File path to the processed spreadsheet data, relative to spreadsheet_data_path
        :param file_path: file path to the processed spreadsheet data, relative to spreadsheet_data_path
        (note that this file is a tab delimited plain text file with the extension working.txt
        :param column_labels_str: A comma delimited listing of the column labels used to identify timepoint and id
        columns.
        :param last_access: A timestamp indicating when the spreadsheet was last accessed (actually last updated)
        :param user_id: The id of the spreadsheet's owner.  Visitors have individual (although more transitory)
        accounts and consequently a user id.
        :param date_uploaded:  The timestamp at which the original spreadsheet was uploaded.
        :param spreadsheet_data_path: path of the folder containing the spreadsheet data, relative to
            the app's configured upload folder
        """
        current_app.logger.info('Setting up spreadsheet object')
        self.descriptive_name = descriptive_name
        self.num_timepoints = num_timepoints
        self.timepoints = timepoints
        self.repeated_measures = repeated_measures
        self.header_row = int(header_row)
        self.original_filename = original_filename
        self.file_mime_type = file_mime_type
        self.file_path = file_path
        self.uploaded_file_path = uploaded_file_path
        self.date_uploaded = date_uploaded
        self.column_labels_str = column_labels_str
        self.last_access = last_access or datetime.datetime.utcnow()
        self.note = ''
        self.spreadsheet_data_path = spreadsheet_data_path
        self.categorical_data = categorical_data
        self.date_uploaded = date_uploaded or datetime.datetime.utcnow()
        self.user_id = user_id

    def setup_processed_spreadsheet(self):
        """
        Create a processed file that is more readily uploaded (compared with Excel files).  This method should be done
        only with a new Spreadsheet is being created de novo - when no processed spreadsheet yet exists.
        """
        self.set_df()
        self.file_path = Spreadsheet.PROCESSED_SPREADSHEET_FILE_PART + "." + Spreadsheet.PROCESSED_SPREADSHEET_FILE_EXT
        self.update_dataframe()

    @timeit
    def init_on_load(self):
        """
        A pandas dataframe is rebuilt from the file
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
                    self.df = pd.read_csv(self.get_processed_file_path(), sep='\t')
                else:
                    self.df = pyarrow.parquet.read_pandas(self.get_processed_file_path()).to_pandas()
            else:
                current_app.logger.warn(f"WARN: no file_path for processed spreadsheet {self.id} - setting up processed spreadsheet automatically")
                self.setup_processed_spreadsheet()
        except Exception as e:
            # The parser failed...we may be able to recover.
            current_app.logger.error(f"Received error during loading of spreadsheet {self.id}")
            current_app.logger.error(e)
            self.df = None
            try:
                self.set_df()

            # If parsing the original fails, we are stuck
            except Exception as e:
                current_app.logger.error(e)
                self.error = True

        self.column_labels = None if not self.column_labels_str else self.column_labels_str.split(",")

        if self.column_labels_str:
            self.identify_columns(self.column_labels)

    def is_categorical(self):
        ''' Returns True if this is a Categorical (MPV) spreadsheet. False if not.'''
        return bool(self.categorical_data)

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
                current_app.logger.info(f"Trying to load excel from {self.get_uploaded_file_path()}")
                self.df = pd.read_excel(str(self.get_uploaded_file_path()),
                                        header=self.header_row - 1,
                                        index_col=False)
            else:
                extension = Spreadsheet.get_file_extension(self.original_filename)
                sep = "\t"
                if extension.lower() in constants.COMMA_DELIMITED_EXTENSIONS:
                    sep = ","
                self.df = pd.read_csv(self.get_uploaded_file_path(),
                                      sep=sep,
                                      header=self.header_row - 1,
                                      index_col=False)
        except (UnicodeDecodeError, ParserError) as e:
            current_app.logger.exception(e)
            raise NitecapException("The file provided could not be parsed.")

    def identify_columns(self, column_labels):
        if self.categorical_data:
            # Categorical / MPV spreadsheet
            self.possible_assignments = self.get_categorical_data_labels()[len(Spreadsheet.NON_DATA_COLUMNS):] # dropping non-data columns
            data_columns = self.get_data_columns(indexes=True)
            self.group_assignments = [self.possible_assignments.index(column_labels[col]) for col in data_columns]

            # Generate the group-membership data for each category variable
            categorical_data = json.loads(self.categorical_data)
            category_labels = [{'variable': category['variable'],
                                 'labels':  [value['name'] for value in category['values']]}
                                for category in categorical_data]
            column_labels = [column_labels[col].split(' ') for col in data_columns]
            self.group_membership = {category['variable']: [category['labels'].index(labels[num]) for labels in column_labels]
                                        for num, category in enumerate(category_labels)}
            return

        # column labels saved as comma delimited string in db
        self.column_labels_str = ",".join(column_labels)
        self.column_labels = column_labels

        self.timepoint_assignments = {col: self.label_to_timepoint(label) for col, label in zip(self.df.columns, self.column_labels)}
        x_values = [value for value in self.timepoint_assignments.values() if value is not None]

        # This is 'x_values' ordered in the same manner as you get from get_data_columns()/get_raw_data()
        self.x_values = [self.timepoint_assignments[col] for col in self.get_data_columns()]

    def get_raw_data(self):
        data_columns = self.get_data_columns()
        return self.df[data_columns]

    def get_data_columns(self, by_day=True, indexes=False):
        ''' Returns list of data columns

        If indexes=True, then the results are the integer indexes into the DF corresponding
        to the data columns, otherwise defaults to giving the strings of the column names.
        For Nitecap timeseries data, by_day=True data columns are ordered by day and time,
        if by_day=False, then they are ordered by time-of-day alone, grouping across days.
        '''
        if self.categorical_data:
            return self.get_mpv_data_columns(indexes=indexes)
        # Order the columns by chronological order
        if not indexes:
            filtered_columns = [(column, label) for column, label in zip(self.df.columns, self.column_labels)
                                if label not in Spreadsheet.NON_DATA_COLUMNS]
        else:
            filtered_columns = [(index, label) for (index, column), label in zip(enumerate(self.df.columns), self.column_labels)
                                if label not in Spreadsheet.NON_DATA_COLUMNS]

        if by_day:
            sorter = lambda col_label: self.label_to_daytime(col_label[1])
        else:
            sorter = lambda col_label: self.label_to_daytime(col_label[1], False)
        ordered_columns = sorted(filtered_columns, key = sorter)
        return [column for column, label in ordered_columns]

    def get_mpv_data_columns(self, indexes=False):
        # Order the columns by group
        possible_labels = self.get_categorical_data_labels()
        if not indexes:
            filtered_columns = [(column, label) for column, label in zip(self.df.columns, self.column_labels)
                                if label not in Spreadsheet.NON_DATA_COLUMNS]
        else:
            filtered_columns = [(index, label) for (index, column), label in zip(enumerate(self.df.columns), self.column_labels)
                                if label not in Spreadsheet.NON_DATA_COLUMNS]
        sorter = lambda col_label: possible_labels.index(col_label[1])
        ordered_columns = sorted(filtered_columns, key = sorter)
        return [column for column, label in ordered_columns]

    def get_id_columns(self, label=False):
        """
        Return the columns corresponding to the selected IDs
        :param label: if True, return column names not column indexes
        :return: list of column indexes corresponding to the ID columns
        """
        id_indices = [index
                      for index, column_label in enumerate(self.column_labels)
                      if column_label == Spreadsheet.ID_COLUMN]
        if label:
            return self.df.columns[id_indices]
        else:
            return id_indices

    def get_ids(self, *args):
        """
        Find all the columns in the spreadsheet's dataframe noted as id columns and concatenate the contents
        of those columns into a numpy series
        :return: a numpy series containing the complete id for each data row.
        """
        if not args:
            id_indices = self.get_id_columns()
        else:
            id_indices = args[0]


        if len(id_indices) == 1:
            return self.df.iloc[:,id_indices[0]].astype(str).tolist()

        # Concatenate the id columns using pandas.Series.str.cat() function
        # convert to type string first since otherwise blank entries will result in float('NaN')
        first_id = id_indices[0]
        concats = self.df.iloc[:,first_id].astype(str).str.cat(self.df.iloc[:,id_indices[1:]].astype(str), ' | ')
        return concats

    def find_unique_ids(self):
        ids = list(self.get_ids())
        return [item for item, count in collections.Counter(ids).items() if count == 1]

    def has_metadata(self):
        ''' Returns whether the spreadsheet metadata has been filled in '''
        if self.is_categorical():
            return (
                self.categorical_data is not '' and
                self.column_labels_str is not ''
            )
        else:
            return (
                self.column_labels_str is not '' and
                self.timepoints is not None and
                self.num_timepoints is not None
            )

    @timeit
    def compute_nitecap(self):
        # Runs NITECAP on the data but just to order the features

        data = self.get_raw_data().values

        # We don't filter any rows out for now
        # however this could be used to use only a subset of rows
        filtered_out = numpy.full(data.shape[0], fill_value=False)

        # Seed the computation so that results are reproducible
        numpy.random.seed(1)

        timepoints = numpy.array(self.x_values)

        # Main nitecap computation
        td, perm_td = nitecap.nitecap_statistics(data, timepoints, self.timepoints,
                                                 repeated_measures=self.repeated_measures,
                                                 N_PERMS=1000)

        # Apply q-value computation but just for the features surviving filtering
        good_td, good_perm_td = td[~filtered_out], perm_td[:,~filtered_out]
        good_q, good_p = nitecap.FDR(good_td, good_perm_td)

        q = numpy.empty(td.shape)
        q[~filtered_out] = good_q
        q[filtered_out] = float("NaN")

        # Compute p-values for ALL features not just the un-filtered ones
        p = nitecap.util.permutation_ps(td, perm_td)

        self.df["nitecap_p"] = p
        self.df["nitecap_q"] = q

        # Other statistics
        # TODO: should users be able to choose their cycle length?
        amplitude, peak_time, trough_time = nitecap.descriptive_statistics(data, timepoints, self.timepoints, cycle_length=self.timepoints)

        self.df["amplitude"] = amplitude
        self.df["peak_time"] = peak_time
        self.df["trough_time"] = trough_time
        self.df["total_delta"] = td
        self.update_dataframe()

    @timeit
    def compute_categorical(self):
        # Runs ANOVA-style computations on the data
        data = self.get_raw_data()

        ps = nitecap.util.anova_on_groups(data.values, self.group_assignments)
        qs = nitecap.util.BH_FDR(ps)
        self.df["anova_p"] = ps
        self.df["anova_q"] = qs
        self.update_dataframe()

    def get_stat_values(self):
        ''' Return dictionary of extra 'stat' values provided as STAT_COLUMNS in the uploaded spreadsheet '''
        stat_columns = [column for column, label in zip(self.df.columns, self.column_labels)
                            if label == Spreadsheet.STAT_COLUMN]
        return self.df[stat_columns]

    @timeit
    def update_dataframe(self):
        if self.file_path.endswith("txt"):
            self.df.to_csv(self.get_processed_file_path(), sep="\t", index=False)
        else:
            # in order to write out, we always need our non-numeric columns to be type string
            # otherwise parquet gives unpredictable results and errors
            str_columns = [col for col,typ in self.df.dtypes.items() if typ == object]
            df = self.df.astype({col: 'str' for col in str_columns})
            pyarrow.parquet.write_table(pyarrow.Table.from_pandas(df, preserve_index=False), self.get_processed_file_path())

    def has_jtk(self):
        meta2d_cols = ['jtk_p', 'jtk_q', 'ars_p', 'ars_q', 'ls_p', 'ls_q']
        if any((c not in self.df.columns) for c in meta2d_cols):
            if self.get_raw_data().shape[1] > MAX_JTK_COLUMNS:
                # Can't compute JTK when there are too many columns
                # it takes too long and will fail
                for col in meta2d_cols:
                    self.df[col] = float("NaN")
                return True
            else:
                return False
        return True

    def increment_edit_version(self):
        ''' Trigger re-computations of anything that needs to be re-computed
        after a metadata change (eg: new column labels)

        Clear JTK computations so that it will be recomputed
        '''

        self.edit_version += 1
        self.save_to_db()

    def validate(self, column_labels):
        """ Check spreadhseet for consistency.

        Validates that we have data in each timepoint"""

        errors = []

        if Spreadsheet.ID_COLUMN not in column_labels:
            errors.append(f"There should be at least one ID column.")

        retained_columns = [column for column, label in zip(self.df.columns, column_labels) if label != 'Ignore']
        type_pattern = re.compile(r"^([a-zA-Z]+)\d*$")
        for retained_column in retained_columns:
            type_match = re.match(type_pattern, str(self.df[retained_column].dtype))
            if not Spreadsheet.ID_COLUMN and (not type_match or type_match.group(1) not in ['int', 'uint', 'float']):
                errors.append(f"Column '{retained_column}' must contain only numerical data to be employed as a timepoint.")

        times = [self.label_to_timepoint(column_daytime) for column_daytime in column_labels]

        # Check that each timepoint has some data
        for i in range(self.num_timepoints):
            if sum(time == i for time in times) == 0:
                day = i // self.num_timepoints
                time_of_day = i % self.timepoints
                errors.append(f"Day {day+1} Timepoint {time_of_day+1} needs at least one column selected")
        return errors

    def validate_categorical(self, column_labels):
        """ Check spreadhseet columns for consistency, in an MPV (categorical) spreadsheet

        Verify that every possible group combination has at least one column
        """
        errors = []
        data_labels = self.get_categorical_data_labels()
        for data_label in data_labels:
            if data_label not in column_labels and data_label not in Spreadsheet.OPTIONAL_COLUMNS:
                errors.append(f"Missing columns of type {data_label}")
        return errors

    def get_sample_dataframe(self):
        mini_df = self.df[:10]
        return mini_df.values.tolist()

    def label_to_daytime(self, label, include_day = True):
        """ returns the day and time of column label """
        match = re.search("Day(\d+) Timepoint(\d+)", label)
        if match:
            d, t = match.groups()
            if include_day:
                return int(d), int(t)
            else:
                return int(t)
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
        return round((os.path.getsize(self.get_uploaded_file_path()) + os.path.getsize(self.get_processed_file_path()))/1E6,3)

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

        spreadsheet_data_path = self.get_spreadsheet_data_folder()
        try:
            if Path(spreadsheet_data_path).exists():
                shutil.rmtree(spreadsheet_data_path)
            else:
                current_app.logger.info(f"Trying to delete spreadhseet {self.id} but no data folder - skipping")
            self.delete_from_db()
        except Exception as e:
            current_app.logger.error(error_message, e)
            error = error_message
        return error

    @staticmethod
    def make_share_copy(spreadsheet, user):
        """
        Makes a complete copy of the spreadsheet to be shared by creating a new spreadsheet using the metadata
        from the original spreadsheet and recursively copying over the directory of the original spreadsheet to
        the new directory assigned to the share.
        :param spreadsheet: the spreadsheet to be shared
        :param user: the recipient of the share
        :return: the new shared spreadsheet
        """

        # Get the user directory path for the user receiving the share and create that user directory if it doesn't
        # already exist.
        user_directory_path = user.get_user_directory_path()
        Path(user_directory_path).mkdir(parents=True, exist_ok=True)

        # Create temporary paths for the share spreadsheet data directory and its included uploaded and processed
        # files and copy over the original spreadsheet data directory.
        temporary_share_spreadsheet_data_path = os.path.join(user_directory_path,  uuid.uuid4().hex)
        shutil.copytree(spreadsheet.spreadsheet_data_path, temporary_share_spreadsheet_data_path)

        # Create the share object - all path reflect the temporary share paths (i.e., paths containing uuid)
        spreadsheet_share = Spreadsheet(descriptive_name=spreadsheet.descriptive_name,
                                        timepoints=spreadsheet.timepoints,
                                        num_timepoints=spreadsheet.num_timepoints,
                                        repeated_measures=spreadsheet.repeated_measures,
                                        header_row=spreadsheet.header_row,
                                        original_filename=spreadsheet.original_filename,
                                        file_mime_type=spreadsheet.file_mime_type,
                                        uploaded_file_path=spreadsheet.uploaded_file_path,
                                        date_uploaded=datetime.datetime.utcnow(),
                                        file_path=spreadsheet.file_path,
                                        column_labels_str=spreadsheet.column_labels_str,
                                        categorical_data=spreadsheet.categorical_data,
                                        last_access=None,
                                        spreadsheet_data_path=temporary_share_spreadsheet_data_path,
                                        user_id=user.id)
        spreadsheet_share.save_to_db()

        # Recover the shared spreadsheet id and rename the spreadsheet data path accordingly.
        spreadsheet_share_data_path = os.path.join(user_directory_path,
                                             spreadsheet_share.get_spreadsheet_data_directory_conventional_name())
        os.rename(temporary_share_spreadsheet_data_path, spreadsheet_share_data_path)

        # Update spreadsheet paths using the spreadsheet id and create the processed spreadsheet and finally, save the
        # updates.
        spreadsheet_share.spreadsheet_data_path = spreadsheet_share_data_path
        spreadsheet_share.save_to_db()

        # Re-upload to s3. Import here to avoid circular import
        from computation.api import store_spreadsheet_to_s3
        spreadsheet_share.init_on_load()
        store_spreadsheet_to_s3(spreadsheet_share)

        return spreadsheet_share

    def get_timepoint_labels(self):
        return set(filter(lambda column_label:
                      column_label != Spreadsheet.ID_COLUMN and column_label != Spreadsheet.IGNORE_COLUMN,
                      self.column_labels))

    @staticmethod
    def join_spreadsheets(spreadsheets):
        ''' Take inner join of multiple spreadsheets

        returns a list of the joined dataframes as well as the appropriate index
        '''
        if len(spreadsheets) == 1:
            # For just a lone spreadsheet, we use all of its rows regardless of
            # the IDs and so for example they don't need to be unique
            dfs = [spreadsheets[0].df]
            combined_index = pd.Index(spreadsheets[0].get_ids())
        else:
            # For more than 1, we take only unique IDs and do an inner join over all the spreadsheets
            # that way they all have the same rows
            combined_index = None
            dfs = []
            for spreadsheet in spreadsheets:
                index = pd.Index(spreadsheet.get_ids())
                df = spreadsheet.df.set_index(index)
                df = df[~index.duplicated()]
                dfs.append(df)

                if combined_index is None:
                    combined_index = df.index
                    continue

                combined_index = combined_index.intersection(df.index)

            # Select only the parts of the data in common to all
            dfs = [df.loc[combined_index] for df in dfs]

        return dfs, combined_index

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

    def get_spreadsheet_data_directory_conventional_name(self):
        """
        Helper method to return the conventional name for this spreadsheet's data directory.  Note that the
        spreadsheet's current spreadsheet data path may be a uuid because the spreadsheet data path is created before
        the spreadsheet object is saved to the db.  So the spreadsheet id is not initially known.
        :return: conventional name for spreadsheet directory.
        """
        return Spreadsheet.SPREADSHEET_DIRECTORY_NAME_TEMPLATE.substitute(spreadsheet_id=self.id)

    def get_spreadsheet_data_directory_name(self):
        """
        Helper method to obtain the spreadsheet data directory name from the spreadsheet data directory path.  Note that
        this is either a uuid or the conventional name depending upon when it is called.
        :return: spreadsheet data directory name
        """
        return os.path.basename(self.spreadsheet_data_path)

    @staticmethod
    def get_processed_spreadsheet_name():
        """
        Helper method to assemble the processed spreadsheet name from the component parts of the file name, which
        are both determined by convention here.
        :return: processed spreadsheet name
        """
        return Spreadsheet.PROCESSED_SPREADSHEET_FILE_PART + "." + Spreadsheet.PROCESSED_SPREADSHEET_FILE_EXT

    def get_processed_file_path(self):
        """
        Returns the absolute path to the processed data file, if any, else None
        """
        if self.file_path == '':
            return None
        return Path(self.get_spreadsheet_data_folder()) / self.file_path

    def get_uploaded_file_path(self):
        """
        Returns the absolute path to the uploaded file, if any, else None
        """
        if self.uploaded_file_path == '':
            return None
        return Path(self.get_spreadsheet_data_folder()) / self.uploaded_file_path

    def get_spreadsheet_data_folder(self):
        """
        Returns the absolute path to the spreadsheet data folder
        """
        return Path(os.environ['UPLOAD_FOLDER']) / self.spreadsheet_data_path

    def get_categorical_data_labels(self):
        """
        Generate possible select options from the categorical data provided for the spreadsheet.  The option list
        contains the id column option and the ignore column option by default.
        :return: list of options to offer for the select inputs of the form requiring the user to specify column
        definitions.
        """
        labels = Spreadsheet.NON_DATA_COLUMNS.copy()

        # One bin per categorical variable.  Each bin contains the possible values for that categorical variable.
        category_bins = []
        categorical_data = json.loads(self.categorical_data)
        for item in categorical_data:

            # Using only the long name for the option list
            values = [value['name'] for value in item['values']]
            category_bins.append(values)

        # Get all combinations across the bins and stringify
        label_data = [' '.join(label_tuple) for label_tuple in list(itertools.product(*category_bins))]
        labels.extend(label_data)
        return labels

    @staticmethod
    def compute_comparison(user, spreadsheets):
        for spreadsheet in spreadsheets:
            spreadsheet.init_on_load()
        dfs, combined_index = Spreadsheet.join_spreadsheets(spreadsheets)

        anova_p = None
        main_effect_p = None
        datasets = []
        timepoints_per_cycle = spreadsheets[0].timepoints
        comparisons_directory = os.path.join(user.get_user_directory_path(), "comparisons")
        for primary, secondary in [(0,1), (1,0)]:
            primary_id, secondary_id = spreadsheets[primary].id, spreadsheets[secondary].id
            file_path = os.path.join(comparisons_directory, f"{primary_id}v{secondary_id}.comparison.parquet")
            # Compute comparisons from scratch
            if not datasets:
                datasets = [df[spreadsheet.get_data_columns()].values for df, spreadsheet in zip(dfs, spreadsheets)]
            repeated_measures = spreadsheets[0].repeated_measures
            for spreadsheet in spreadsheets:
                if spreadsheet.repeated_measures != repeated_measures:
                    error = f"Attempted comparison of Spreadsheets {primary_id} and {secondary_id} that do not match in whether they are repeated measures."
                    current_app.logger.warn(error)
                    return error, 500

            # Run the actual upside calculation
            upside_p = nitecap.upside.main(spreadsheets[primary].x_values, datasets[primary],
                                           spreadsheets[secondary].x_values, datasets[secondary],
                                           timepoints_per_cycle,
                                            repeated_measures=repeated_measures)
            upside_q = nitecap.util.BH_FDR(upside_p)

            if anova_p is None or main_effect_p is None:
                # Run two-way anova
                groups_A = numpy.array(spreadsheets[primary].x_values) % timepoints_per_cycle
                groups_B = numpy.array(spreadsheets[secondary].x_values) % timepoints_per_cycle
                anova_p, main_effect_p = nitecap.util.two_way_anova( groups_A, datasets[primary],
                                                                     groups_B, datasets[secondary])
                anova_q = nitecap.util.BH_FDR(anova_p)
                main_effect_q = nitecap.util.BH_FDR(main_effect_p)

                # Run Cosinor analysis
                amplitude_p, phase_p = nitecap.util.cosinor_analysis(spreadsheets[primary].x_values, datasets[primary],
                                                                     spreadsheets[secondary].x_values, datasets[secondary],
                                                                     timepoints_per_cycle)
                phase_q = nitecap.util.BH_FDR(phase_p)
                amplitude_q = nitecap.util.BH_FDR(amplitude_p)

            comp_data = pd.DataFrame(index=combined_index)
            comp_data["upside_p"] = upside_p
            comp_data["upside_q"] = upside_q
            comp_data["two_way_anova_p"] = anova_p
            comp_data["two_way_anova_q"] = anova_q
            comp_data["main_effect_p"] = main_effect_p
            comp_data["main_effect_q"] = main_effect_q
            comp_data["phase_p"] = phase_p
            comp_data["phase_q"] = phase_q
            comp_data["amplitude_p"] = amplitude_p
            comp_data["amplitude_q"] = amplitude_q


            #  First reload the spreadsheets to make sure they haven't been edited
            new_spreadsheets = [spreadsheet.user.find_user_spreadsheet_by_id(spreadsheet.id) for spreadsheet in spreadsheets]
            if any(new.edit_version != old.edit_version for new, old in zip(new_spreadsheets, spreadsheets)):
                raise RuntimeError(f"Comparison of spreadsheets {[s.id for s in spreadsheets]} was out-dated by the time it was computed")

            # Save to disk
            pyarrow.parquet.write_table(pyarrow.Table.from_pandas(comp_data), file_path)

            current_app.logger.info(f"Computed upside values and saved them to file {file_path}")

    @staticmethod
    def get_file_extension(filename):
        ''' Checks if a filename has a suffix matching our allowed extensions and if so, return that.
        Returns None if no valid extension found

        In particular, this returns 'txt.gz' for those files and not .gz like a '''

        name = str(filename).lower()
        matches = [ext for ext in constants.ALLOWED_EXTENSIONS
                    if name.endswith(ext)]

        if matches:
            return matches[0]
        else:
            return None

column_label_formats = [re.compile(r"CT(\d+)"), re.compile(r"ct(\d)"),
                        re.compile(r"(\d+)CT"), re.compile(r"(\d)ct"),
                        re.compile(r"ZT(\d+)"), re.compile(r"zt(\d+)"),
                        re.compile(r"(\d+)ZT"), re.compile(r"(\d+)zt")]
