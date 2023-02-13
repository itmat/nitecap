import collections
import datetime
import itertools
import json
import os
import shutil
import uuid
from typing import Optional, TYPE_CHECKING
from pandas.errors import ParserError
from cloudpathlib import AnyPath as Path
import re
from string import Template

import pandas as pd
import pyarrow
import pyarrow.parquet
import constants


from db import db
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from exceptions import NitecapException
import nitecap.util
from flask import current_app
if TYPE_CHECKING:
    from models.users.user import User

from timer_decorator import timeit

class Spreadsheet(db.Model):
    __tablename__ = "spreadsheets"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    descriptive_name: Mapped[str] = mapped_column(String(250))
    num_timepoints: Mapped[Optional[int]]
    timepoints: Mapped[Optional[int]]
    repeated_measures: Mapped[bool] = mapped_column(default=False)
    header_row: Mapped[int] = mapped_column(default=1)
    original_filename: Mapped[str] = mapped_column(String(250))
    file_mime_type: Mapped[str] = mapped_column(String(250))
    file_path: Mapped[Optional[str]] = mapped_column(String(250))
    uploaded_file_path: Mapped[str] = mapped_column(String(250))
    date_uploaded: Mapped[datetime.datetime]
    column_labels: Mapped[list[str]] = mapped_column(ARRAY(String(250)), default=list)
    last_access: Mapped[datetime.datetime]
    note: Mapped[Optional[str]] = mapped_column(String(5000))
    spreadsheet_data_path: Mapped[str] = mapped_column(String(250))
    categorical_data: Mapped[Optional[str]] = mapped_column(String(5000))
    user_id: Mapped[uuid.UUID] = mapped_column(db.ForeignKey("users.id"))
    user: Mapped["User"] = relationship(back_populates="_spreadsheets")
    edit_version: Mapped[int] = mapped_column(default=0)

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
                 file_mime_type, uploaded_file_path, date_uploaded, user_id, file_path=None,
                 column_labels=None, last_access=None,
                 spreadsheet_data_path='', categorical_data=''):
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
        :param column_labels: A comma delimited listing of the column labels used to identify timepoint and id
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
        self.column_labels = column_labels or list()
        self.last_access = last_access or datetime.datetime.utcnow()
        self.note = ''
        self.spreadsheet_data_path = spreadsheet_data_path
        self.categorical_data = categorical_data
        self.date_uploaded = date_uploaded
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

        if len(self.column_labels) > 0:
            self.identify_columns()

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

    def set_column_labels(self, column_labels):
        self.column_labels = column_labels
        self.identify_columns()

    def identify_columns(self):
        if self.categorical_data:
            # Categorical / MPV spreadsheet
            self.possible_assignments = self.get_categorical_data_labels()[len(Spreadsheet.NON_DATA_COLUMNS):] # dropping non-data columns
            data_columns = self.get_data_columns(indexes=True)
            self.group_assignments = [self.possible_assignments.index(self.column_labels[col]) for col in data_columns]

            # Generate the group-membership data for each category variable
            categorical_data = json.loads(self.categorical_data)
            category_labels = [{'variable': category['variable'],
                                 'labels':  [value['name'] for value in category['values']]}
                                for category in categorical_data]
            column_labels = [self.column_labels[col].split(' ') for col in data_columns]
            self.group_membership = {category['variable']: [category['labels'].index(labels[num]) for labels in column_labels]
                                        for num, category in enumerate(category_labels)}
            return

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
        :return: a list containing the complete id for each data row.
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
        concats = self.df.iloc[:,first_id].astype(str).str.cat(self.df.iloc[:,id_indices[1:]].astype(str), ' | ').tolist()
        return concats

    def has_metadata(self):
        ''' Returns whether the spreadsheet metadata has been filled in '''
        if self.is_categorical():
            return (
                self.categorical_data != '' and
                len(self.column_labels) > 0
            )
        else:
            return (
                len(self.column_labels) > 0 and
                self.timepoints is not None and
                self.num_timepoints is not None
            )

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

        temporary_spreadsheet_folder_name = f"{uuid.uuid4().hex}"
        temporary_share_spreadsheet_data_path = Path(user.get_user_directory_path()) / temporary_spreadsheet_folder_name
        relative_temporary_share_spreadsheet_data_path = Path(user.get_user_directory_name()) / temporary_spreadsheet_folder_name


        # Create temporary paths for the share spreadsheet data directory and its included uploaded and processed
        # files and copy over the original spreadsheet data directory.
        shutil.copytree(
            spreadsheet.get_spreadsheet_data_folder(),
            temporary_share_spreadsheet_data_path,
        )

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
                                        column_labels=spreadsheet.column_labels,
                                        categorical_data=spreadsheet.categorical_data,
                                        last_access=None,
                                        spreadsheet_data_path=str(relative_temporary_share_spreadsheet_data_path),
                                        user_id=user.id)
        spreadsheet_share.save_to_db()

        # Recover the shared spreadsheet id and rename the spreadsheet data path accordingly.

        spreadsheet_folder_name = spreadsheet_share.get_spreadsheet_data_directory_conventional_name()
        spreadsheet_share_data_path = Path(user.get_user_directory_path()) / spreadsheet_folder_name
        os.rename(temporary_share_spreadsheet_data_path, spreadsheet_share_data_path)
        relative_spreadsheet_share_data_path = Path(user.get_user_directory_name()) / spreadsheet_folder_name

        # Update spreadsheet paths using the spreadsheet id and create the processed spreadsheet and finally, save the
        # updates.
        spreadsheet_share.spreadsheet_data_path = str(relative_spreadsheet_share_data_path)
        spreadsheet_share.save_to_db()

        # Re-upload to s3. Import here to avoid circular import
        from computation.api import store_spreadsheet_to_s3
        if spreadsheet.has_metadata():
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
        and a list of the row numbers that the joined rows originally came from
        '''
        if len(spreadsheets) == 1:
            # For just a lone spreadsheet, we use all of its rows regardless of
            # the IDs and so for example they don't need to be unique
            dfs = [spreadsheets[0].df]
            combined_index = pd.Index(spreadsheets[0].get_ids())
            row_numbers = [spreadsheets[0].df.index.to_list()]
        else:
            # For more than 1, we take only unique IDs and do an inner join over all the spreadsheets
            # that way they all have the same rows
            combined_index = None
            dfs = []
            rows_list = []
            for spreadsheet in spreadsheets:
                index = pd.Index(spreadsheet.get_ids())
                index_to_rows = pd.Series(spreadsheet.df.index, index=index)
                df = spreadsheet.df.set_index(index)
                df = df[~index.duplicated()]
                index_to_rows = index_to_rows[~index.duplicated()]
                dfs.append(df)
                rows_list.append(index_to_rows)

                if combined_index is None:
                    combined_index = df.index
                else:
                    combined_index = combined_index.intersection(df.index)

            # Select only the parts of the data in common to all
            dfs = [df.loc[combined_index] for df in dfs]
            row_numbers = [rows.loc[combined_index] for rows in rows_list]

        return dfs, combined_index, row_numbers

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
