import json
import datetime
import multiprocessing

from sqlalchemy import orm

from db import db
from models.users.user import User
from flask import current_app

# Number of processes allowed to do work at once
NUM_WORKERS = 1

class Job(db.Model):
    __tablename__ = 'jobs'
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(15), nullable=False)
    params = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), nullable=False)
    start_time = db.Column(db.DateTime)
    queue_time = db.Column(db.DateTime)

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

        num_running = Job.query.filter_by(status="running").count()
        if num_running >= NUM_WORKERS:
            # Too many workers running, we can't do this task right now
            # have to try again later
            #TODO: timeout old jobs?
            return 'waiting'

        # Mark ourself as running
        self.status = "running"
        db.session.add(self)
        db.session.commit()

        # Start the process
        process = multiprocessing.Process(target = run_job, args=(self.type, self.params))
        process.spawn()

        return 'running'

    @classmethod
    def find_or_make(cls, job_type, params):
        params = json.dumps(params)
        job = cls.query.filter_by(type=job_type, params=params).first()
        if not job:
            job = Job(job_type, params)
        return job

def run_job(job_type, params):
    function = job_functions[job_type]
    try:
        function(params)
    except Exception as e:
        # TODO Log this
        print(f"Exception occured in Job {job_type}: {params}")
        print(e)
        status = "failed"
    else:
        status = "completed"

    # Update the status in our Job DB entry
    job = Job.find_by_params(job_type, params)
    if job is None:
        # Our Job entry got lost, create a completed one
        job = Job(job_type, params, status=status)
    job.status = status

    db.session.add(job)
    db.session.commit()

def compute_jtk(params):
    ''' job to trigger the computation of jtk

    params: list of user id, spreadsheet id, and spreadsheet edit version
    '''
    user_id, spreadsheet_id, edit_version = json.loads(params)

    user = User.find_by_id(user_id)
    spreadsheet = user.find_user_spreadsheet_by_id(spreadsheet_id)
    spreadsheet.compute_jtk()

job_functions = {
    "jtk": compute_jtk,
}

