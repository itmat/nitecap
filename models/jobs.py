import json
import datetime
import multiprocessing

from sqlalchemy import orm

from db import db
from models.users.user import User
from models.spreadsheets.spreadsheet import Spreadsheet
from flask import current_app

class Job(db.Model):
    __tablename__ = 'jobs'
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(15), nullable=False)
    params = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), nullable=False)
    start_time = db.Column(db.DateTime)

    def __init__(self, job_type, params, status="unknown"):
        """
        A 'dumb' Job task status that limits how many can be run at once

        When a job is started, it records its running status in the DB
        If there are too many jobs currently running, it just returns 'waiting'
        but does NOT queue up the job. The process that wants the job done must
        continue to ask for its status in order for it to be run.

        Jobs change status to 'completed' or 'failed' after the process finishes

        statuses:
        'unknown': not yet determined
        'waiting': not in DB, not started (not queued), must be resubmitted
        'running': in DB as running, process was started
        'failed': process had an error
        'completed': process completed successfully
        """
        self.type = job_type
        self.params = json.dumps(params)
        self.status = status

        assert self.type in job_functions

    def run(self):
        if self.status in ['running', 'completed', 'failed']:
            # Task has already been executed
            return self.status

        num_running = Job.get_number_running_jobs()
        if num_running >= current_app.config['NUM_JOB_WORKERS']:
            # Too many workers running, we can't do this task right now
            # have to try again later
            return 'waiting'

        # Mark ourself as running
        self.status = "running"
        self.start_time = datetime.datetime.utcnow()
        db.session.add(self)
        db.session.commit()

        # Start the process
        process = multiprocessing.Process(target = run_job, args=(self.type, self.params))
        process.start()

        return 'running'

    @classmethod
    def get_number_running_jobs(cls):
        # First we cleanup the old jobs
        # deleting ones that are super old
        drop_threshold = datetime.datetime.utcnow() - current_app.config['JOB_DROP_TIME']*datetime.timedelta(seconds=1)

        num_dead = Job.query.filter(Job.start_time < drop_threshold).delete(synchronize_session='fetch')
        if num_dead > 0:
            current_app.logger.info(f"Removing {num_dead} old jobs")

        # and timeout those that are running too long
        timeout_threshold = datetime.datetime.utcnow() - current_app.config['JOB_TIMEOUT']*datetime.timedelta(seconds=1)
        jobs_timedout = Job.query.filter_by(status="running").filter(Job.start_time <  timeout_threshold).update({Job.status:  "timed_out"}, synchronize_session='fetch')
        if jobs_timedout > 0:
            current_app.logger.warning(f"TIMEOUT for {jobs_timedout} jobs")

        num_running = Job.query.filter_by(status="running").count()
        db.session.commit()

        return num_running


    @classmethod
    def find_or_make(cls, job_type, params):
        params_json = json.dumps(params)
        job = cls.query.filter_by(type=job_type, params=params_json).first()
        if not job:
            job = Job(job_type, params)
        return job

def run_job(job_type, params):
    function = job_functions[job_type]
    current_app.logger.info(f"Starting Job {job_type}: {params}")
    params_value = json.loads(params)
    try:
        function(params_value)
    except Exception as e:
        current_app.logger.error(f"Exception occured in Job {job_type}: {params}")
        current_app.logger.error(e)
        status = "failed"
    else:
        status = "completed"

    current_app.logger.info(f"Finished Job {job_type}: {params} with status {status}")

    # Update the status in our Job DB entry
    job = Job.find_or_make(job_type, params_value)
    job.status = status

    db.session.add(job)
    db.session.commit()

def compute_jtk(params):
    ''' job to trigger the computation of jtk

    params: list of user id, spreadsheet id, and spreadsheet edit version
    '''
    user_id, spreadsheet_id, edit_version = params

    user = User.find_by_id(user_id)
    spreadsheet = user.find_user_spreadsheet_by_id(spreadsheet_id)
    spreadsheet.compute_jtk()

def compute_comparison(params):
    ''' job to trigger the computation of comparison

    params: list of user id, spreadsheet ids, and spreadsheet edit versions
    '''
    user_id, spreadsheet_ids, edit_versions = params

    user = User.find_by_id(user_id)

    # Check user ownership over these spreadsheets
    spreadsheets = []
    for spreadsheet_id in spreadsheet_ids:
        spreadsheet = user.find_user_spreadsheet_by_id(spreadsheet_id)
        if not spreadsheet:
            current_app.logger.warn(f"Attempted access for spreadsheet {spreadsheet_id} not owned by user {user.id}")
        spreadsheets.append(spreadsheet)

    Spreadsheet.compute_comparison(user, spreadsheets)

job_functions = {
    "jtk": compute_jtk,
    "comparison": compute_comparison,
}

