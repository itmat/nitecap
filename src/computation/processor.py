from itertools import chain
from multiprocessing import Pipe, Process
from multiprocessing.connection import wait

from notifier import notifier


def run(job, algorithm, data, parameters):
    two_percent = job["size"] // 50 or 1

    def data_slice():
        for processed, i in enumerate(range(job["start_index"], job["end_index"])):
            if processed % two_percent == 0:
                job["child_connection"].send(
                    {
                        "status": "RUNNING",
                        "number_of_processed_items": processed,
                    }
                )
            yield data[i]

    try:
        result = algorithm(data_slice(), *parameters)
    except Exception as exception:
        result = exception

    job["child_connection"].send({"status": "COMPLETED", "result": result})
    job["child_connection"].close()


def parallel_compute(
    algorithm, data, *parameters, send_notification, number_of_processors=6
):
    if isinstance(data, tuple):
        data = MultipleSpreadsheet(data)

    workload_size = len(data)

    jobs = []
    for i in range(number_of_processors):
        parent_connection, child_connection = Pipe(False)
        jobs.append(
            {
                "parent_connection": parent_connection,
                "child_connection": child_connection,
                "number_of_processed_items": 0,
                "process": None,
                "result": None,
            }
        )

    for i in range(number_of_processors):
        jobs[i]["start_index"] = i * (workload_size // number_of_processors)
        jobs[i]["end_index"] = (i + 1) * (workload_size // number_of_processors)

    for i in range(workload_size % number_of_processors):
        jobs[i]["start_index"] += i
        jobs[i]["end_index"] += i + 1

    for job in jobs:
        job["size"] = job["end_index"] - job["start_index"]

    # Start the notifier
    notifier_parent_connection, notifier_child_connection = Pipe()
    notifier_process = Process(
        target=notifier,
        args=(notifier_child_connection, workload_size, send_notification),
    )
    notifier_process.start()

    # Start jobs
    running = {}
    for job in jobs:
        process = Process(target=run, args=(job, algorithm, data, parameters))
        job["process"] = process
        running[job["parent_connection"]] = job
        process.start()

    # Wait for jobs to complete
    while running:
        connections = chain(running, [notifier_parent_connection])
        for connection in wait(connections):
            message = connection.recv()

            if isinstance(message, Exception):
                raise message

            if message == "PROGRESS_UPDATE_REQUEST":
                notifier_parent_connection.send(
                    sum(job["number_of_processed_items"] for job in jobs)
                )
            else:
                job = running[connection]
                if message["status"] == "RUNNING":
                    job["number_of_processed_items"] = message[
                        "number_of_processed_items"
                    ]

                if message["status"] == "COMPLETED":
                    job["result"] = message["result"]
                    job["number_of_processed_items"] = job["size"]
                    del running[connection]

    send_notification({"status": "FINALIZING"})

    notifier_parent_connection.send("EXIT")
    notifier_parent_connection.close()

    for job in jobs:
        job["parent_connection"].close()
        job["process"].join()

    notifier_process.join()

    results = list(
        map(list, map(chain.from_iterable, zip(*(job["result"] for job in jobs))))
    )

    return results if len(results) > 1 else results.pop()


class MultipleSpreadsheet:
    def __init__(self, data):
        self.spreadsheets = data

    def __len__(self):
        return len(self.spreadsheets[0])

    def __getitem__(self, i):
        return (spreadsheet[i] for spreadsheet in self.spreadsheets)
