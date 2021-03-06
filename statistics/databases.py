"""Database classes and support for measurements"""

from abc import ABC
import json
import logging
import os
import re
import sys
import time
import numpy as np
from typing import Tuple

from google.cloud import bigquery

logging.basicConfig(level=logging.INFO)


def get_database(style: str):
    """Retrieve database to the database to be used
    Returns database client, database object, Integer type to be used
    and a connection object (for Azure)
    """

    conn = None
    if style == "ms":
        logging.info("Using Microsoft Azure backend")
        server = "mysupertestserver.database.windows.net"
        database = "mysupertestdatabase"
        username = "mysupertestadmin"
        password = "not_here"

        import pymssql

        conn = pymssql.connect(server, username, password, database)
        client = conn.cursor(as_dict=True)
        dbo = "dbo"
        integer = "INTEGER"

    elif style == "google":
        logging.info("Using Google Big Query backend")
        client = bigquery.Client()
        dbo = "ADataSet"
        integer = "INT64"

    elif style == "none":
        logging.info("Using No Backend")
        dbo = "Nopedb"
        integer = "Nopeint"
        client = None

    else:
        logging.error("Error in configuring database")
        sys.exit(1)

    return client, dbo, integer, conn


# Keep all this in case we want real SQL publshing again

# cpu_table = "ci_cpu_measurement_tedge_mapper"
# mem_table = "ci_mem_measurement_tedge_mapper"
# cpu_hist_table = "ci_cpu_hist"


# def myquery(client, query, conn, style):
#
#    logging.info(query)
#
#    if style == "ms":
#        client.execute(query)
#        conn.commit()
#
#    elif style == "google":
#
#        query_job = client.query(query)
#        if query_job.errors:
#            logging.error("Error", query_job.error_result)
#            sys.exit(1)
#        time.sleep(0.3)
#    elif style == "none":
#        pass
#    else:
#        sys.exit(1)


# def get_sql_create_cpu_table(dbo, name, integer):
#     create_cpu = f"""
#     CREATE TABLE {dbo}.{name} (
#     id {integer},
#     mid {integer},
#     sample {integer},
#     utime                    {integer},
#     stime                    {integer},
#     cutime                   {integer},
#     cstime                   {integer}
#     );
#     """


# def get_sql_create_mem_table(dbo, name, integer):

#     create_mem = f"""
#     CREATE TABLE {dbo}.{name} (
#     id {integer},
#     mid {integer},
#     sample {integer},
#     size {integer},
#     resident {integer},
#     shared {integer},
#     text {integer},
#     data {integer}
#     );
#     """


# def get_sql_create_mem_table(dbo, name, integer):
#     create_cpu_hist = f"""
#     CREATE TABLE {dbo}.{name} (
#     id {integer},
#     last                    {integer},
#     old                     {integer},
#     older                   {integer},
#     evenolder                   {integer},
#     evenmovreolder                   {integer}
#     );
#     """


# def get_sql_create_mem_table(dbo, name, client):
#     myquery(client, f"drop table {dbo}.{cpu_table}")


# def get_sql_create_mem_table(dbo, name, client):
#     myquery(client, f"drop table {dbo}.{mem_table}")


# def get_sql_create_mem_table(dbo, name, client):
#     myquery(client, f"drop table {dbo}.{cpu_hist_table}")


class MeasurementBase(ABC):
    """Abstract base class for type Measurements"""

    def __init__(self, lake, name, data_amount, data_length, client, testmode):

        # Amount of columns in the table
        self.data_amount = data_amount

        # Length of the measurement in seconds
        self.data_length = data_length

        self.size = data_length * data_amount

        self.client = client
        self.lake = lake
        self.json_data = None
        self.job_config = None

        if testmode:
            self.name = name + "_test"
        else:
            self.name = name

        self.database = f"thin-edge-statistics.ThinEdgeDataSet.{self.name}"

    def postprocess(self, folders, testname, filename, binary):
        """Postprocess all relevant folders"""

    def show(self):
        """Show content on console"""

    def update_table(self):
        """Create table and prepare loading via json and upload"""

    def delete_table(self):
        """Delete the table from the cloud"""
        try:
            self.client.delete_table(self.database)
        except:  # TODO: Can' import this google.api_core.exceptions.NotFound:
            pass

    def upload_table(self):
        """Upload table to online database"""

        if self.client:
            load_job = self.client.load_table_from_json(
                self.json_data,
                self.database,
                job_config=self.job_config,
            )

            while load_job.running():
                time.sleep(0.5)
                logging.info("Waiting")

            if load_job.errors:
                logging.error("Error %s", load_job.error_result)
                logging.error(load_job.errors)
                raise SystemError

    @staticmethod
    def foldername_to_index(foldername: str) -> int:
        """Convert results_N_unpack into N"""
        reg = re.compile(r"^results_(\d+)_unpack$")
        match = reg.match(foldername)

        if match:
            index = int(match.group(1))
        else:
            raise SystemError("Cannot convert foldername")

        return index


class MeasurementMetadata(MeasurementBase):
    """Class to represent a table of measurement metadata"""

    def __init__(self, lake, name, data_amount, data_length, client, testmode):

        super().__init__(lake, name, data_amount, data_length, client, testmode)
        self.array = np.zeros((self.size, 7), dtype=np.int32)
        self.row_id = 0

        self.array = []
        self.client = client

    def scrap_data(self, file: str) -> Tuple[str, str, str, str, str]:
        """Read measurement data from file"""

        with open(file) as content:
            data = json.load(content)
            run = data["run_number"]
            date = data["updated_at"]
            url = data["html_url"]
            name = data["name"]
            branch = data["head_branch"]

        return run, date, url, name, branch

    def postprocess(self, folders):
        """Postprocess all relevant folders"""
        idx = 0
        for folder in folders:
            index = self.foldername_to_index(folder)

            name = f"system_test_{index}_metadata.json"
            path = os.path.join(self.lake, name)

            run, date, url, name, branch = self.scrap_data(path)

            self.array.append((idx, run, date, url, name, branch))
            idx += 1

        return self.array

    def show(self):
        """Show content on console"""
        logging.info("Content of table %s", self.database)
        for row in self.array:
            logging.info(row)

    def update_table(self):
        """Create table and prepare loading via json and upload"""

        logging.info("Updating table: %s", self.name)

        self.delete_table()

        self.job_config = bigquery.LoadJobConfig(
            schema=[
                bigquery.SchemaField("id", "INT64"),
                bigquery.SchemaField("mid", "INT64"),
                bigquery.SchemaField("date", "STRING"),
                bigquery.SchemaField("url", "STRING"),
                bigquery.SchemaField("name", "STRING"),
                bigquery.SchemaField("branch", "STRING"),
            ],
        )

        self.json_data = []

        for index in range(self.data_amount):
            self.json_data.append(
                {
                    "id": self.array[index][0],
                    "mid": self.array[index][1],
                    "date": self.array[index][2],
                    "url": self.array[index][3],
                    "name": self.array[index][4],
                    "branch": self.array[index][5],
                }
            )

        self.upload_table()


class CpuHistory(MeasurementBase):
    """Class to represent a table of measured CPU usage"""

    def __init__(self, lake, name, data_amount, data_length, client, testmode):

        super().__init__(lake, name, data_amount, data_length, client, testmode)
        self.array = np.zeros((self.size, 7), dtype=np.int32)

        # The current row index
        self.row_id = 0

    def scrap_zeros(self, measurement_index):
        """Fill a measurement with zeros"""

        sample = 0
        for i in range(self.data_length):

            utime = 0
            stime = 0
            cutime = 0  # cutime
            cstime = 0  # cstime

            self.insert_line(
                idx=self.row_id,
                mid=measurement_index,
                sample=sample,
                utime=utime,
                stime=stime,
                cutime=cutime,
                cstime=cstime,
            )
            sample += 1
            self.row_id += 1

    def scrap_data_collectd(self, file_utime, file_stime, measurement_index):
        """Read measurement data from collectd export"""

        sample = 0
        try:
            with open(file_utime) as thestats_utime:
                with open(file_stime) as thestats_stime:
                    lines_utime = thestats_utime.readlines()
                    lines_stime = thestats_stime.readlines()

                    assert len(lines_utime) == self.data_length
                    assert len(lines_stime) == self.data_length

                    for i in range(self.data_length):

                        timestamp_utime, utime_str = lines_utime[i].split()
                        timestamp_stime, stime_str = lines_stime[i].split()

                        if timestamp_utime != timestamp_stime:
                            print(
                                f"Warning timestamps are not equal {timestamp_utime} and {timestamp_stime}"
                            )

                        if utime_str == "None":
                            utime = 0
                        else:
                            utime = int(float(utime_str))

                        if stime_str == "None":
                            stime = 0
                        else:
                            stime = int(float(stime_str))

                        cutime = (
                            0  # glue cutime to zero, we do not have child processes
                        )
                        cstime = (
                            0  # glue cstime to zero, we do not have child processes
                        )

                        self.insert_line(
                            idx=self.row_id,
                            mid=measurement_index,
                            sample=sample,
                            utime=utime,
                            stime=stime,
                            cutime=cutime,
                            cstime=cstime,
                        )
                        sample += 1
                        self.row_id += 1

        except FileNotFoundError as err:
            logging.warning("File not found, skipping for now! %s", str(err))

        missing = self.data_length - sample

        assert missing == 0

    def scrap_data(self, thefile, measurement_index, binary):
        """Read measurement data from file /proc/pid/stat

        See manpage proc ($ man proc) in section /proc/[pid]/stat for colum descriptions
        """

        sample = 0
        try:
            with open(thefile) as thestats:
                lines = thestats.readlines()
                for line in lines:
                    entries = line.split()
                    # In some cases there some entries from /proc/stat here.
                    # This can happen when the pid is not existing anymore
                    # then /proc/pid/stat is evaluated to /proc/stat
                    # We just filter here to match the right lines.
                    if len(entries) == 52 and entries[1] == f"({binary})":
                        # It can happen that there are 61 lines measured
                        # e.g. in the 60s interval, we just ignore them
                        if sample >= self.data_length:
                            logging.warning(
                                "Omitted a sample from mid %s", measurement_index
                            )
                            continue
                        utime = int(entries[13])  # utime
                        stime = int(entries[14])  # stime
                        cutime = int(entries[15])  # cutime
                        cstime = int(entries[16])  # cstime

                        self.insert_line(
                            idx=self.row_id,
                            mid=measurement_index,
                            sample=sample,
                            utime=utime,
                            stime=stime,
                            cutime=cutime,
                            cstime=cstime,
                        )
                        sample += 1
                        self.row_id += 1

        except FileNotFoundError as err:
            logging.warning("File not found, skipping for now! %s", str(err))

        # In case that there are not enough lines in the file fix with zeros
        # Can happen, depending on when the data recorder process is killed.

        missing = self.data_length - sample

        for miss in range(missing):
            self.insert_line(
                idx=self.row_id,
                mid=measurement_index,
                sample=sample,
                utime=0,
                stime=0,
                cutime=0,
                cstime=0,
            )
            sample += 1
            self.row_id += 1

    def postprocess(self, folders, testname, filename, binary):

        """Postprocess all relevant folders"""
        for folder in folders:
            index = self.foldername_to_index(folder)

            statsfile = (
                f"{self.lake}/{folder}/PySys/{testname}/Output/linux/{filename}.out"
            )

            if filename == "stat_mapper_stdout":
                filename_rrd1 = "gauge-mapper-c8y-utime"
                filename_rrd2 = "gauge-mapper-c8y-stime"
            elif filename == "stat_mosquitto_stdout":
                filename_rrd1 = "gauge-mosquitto-utime"
                filename_rrd2 = "gauge-mosquitto-stime"
            else:

                raise SystemError("Cannot convert filename %s" % filename)

            rrdfile1 = f"{self.lake}/{folder}/PySys/analytics/{testname}/Output/linux/{filename_rrd1}.rrd.txt"
            rrdfile2 = f"{self.lake}/{folder}/PySys/analytics/{testname}/Output/linux/{filename_rrd2}.rrd.txt"

            # After moving tests into folders
            rrdfile1_old = f"{self.lake}/{folder}/PySys/{testname}/Output/linux/{filename_rrd1}.rrd.txt"
            rrdfile2_old = f"{self.lake}/{folder}/PySys/{testname}/Output/linux/{filename_rrd2}.rrd.txt"

            if os.path.exists(statsfile):
                self.scrap_data(statsfile, index, binary)
            elif os.path.exists(rrdfile1):
                self.scrap_data_collectd(rrdfile1, rrdfile2, index)
            elif os.path.exists(rrdfile1_old):
                self.scrap_data_collectd(rrdfile1_old, rrdfile2_old, index)
            else:
                # breakpoint()
                # raise SystemError("File does not exist !!!")
                logging.info(
                    "CPU history file does not exist! %s or %s or %s" % (statsfile, rrdfile1, rrdfile2)
                )
                logging.info("Filling with zeros")
                self.scrap_zeros(index)

    def insert_line(self, idx, mid, sample, utime, stime, cutime, cstime):
        """Insert a line into the table"""
        self.array[idx] = [idx, mid, sample, utime, stime, cutime, cstime]

    def show(self):
        """Show content with matplotlib"""
        import matplotlib.pyplot as plt

        fig, axis = plt.subplots()

        axis.plot(self.array[:, 1], ".", label="mid")
        axis.plot(self.array[:, 2], "-", label="sample")
        axis.plot(self.array[:, 3], "-", label="utime")
        axis.plot(self.array[:, 4], "-", label="stime")
        axis.plot(self.array[:, 5], "-", label="cutime")
        axis.plot(self.array[:, 6], "-", label="cstime")
        plt.legend()
        plt.title("CPU History  " + self.name)

        plt.show()

    def update_table(self):
        """Create table and prepare loading via json and upload"""
        logging.info("Updating table: %s", self.name)
        self.delete_table()

        self.job_config = bigquery.LoadJobConfig(
            schema=[
                bigquery.SchemaField("id", "INT64"),
                bigquery.SchemaField("mid", "INT64"),
                bigquery.SchemaField("sample", "INT64"),
                bigquery.SchemaField("utime", "INT64"),
                bigquery.SchemaField("stime", "INT64"),
                bigquery.SchemaField("cutime", "INT64"),
                bigquery.SchemaField("cstime", "INT64"),
            ],
        )

        self.json_data = []

        for i in range(self.size):
            self.json_data.append(
                {
                    "id": int(self.array[i, 0]),
                    "mid": int(self.array[i, 1]),
                    "sample": int(self.array[i, 2]),
                    "utime": int(self.array[i, 3]),
                    "stime": int(self.array[i, 4]),
                    "cutime": int(self.array[i, 5]),
                    "cstime": int(self.array[i, 6]),
                }
            )

        self.upload_table()


class CpuHistoryStacked(MeasurementBase):
    """Class to represent a table of measured CPU usage as stacked graph.
    The graph contains user and system cpu time for the last N test-runs.
    """

    def __init__(self, lake, name, data_amount, data_length, client, testmode):

        super().__init__(lake, name, data_amount, data_length, client, testmode)

        self.row_id = 0

        self.history = 10  # process the last 10 test runs
        self.fields = [
            ("id", "INT64"),
            ("t0u", "INT64"),
            ("t0s", "INT64"),
            ("t1u", "INT64"),
            ("t1s", "INT64"),
            ("t2u", "INT64"),
            ("t2s", "INT64"),
            ("t3u", "INT64"),
            ("t3s", "INT64"),
            ("t4u", "INT64"),
            ("t4s", "INT64"),
            ("t5u", "INT64"),
            ("t5s", "INT64"),
            ("t6u", "INT64"),
            ("t6s", "INT64"),
            ("t7u", "INT64"),
            ("t7s", "INT64"),
            ("t8u", "INT64"),
            ("t8s", "INT64"),
            ("t9u", "INT64"),
            ("t9s", "INT64"),
        ]
        self.array = np.zeros((self.data_length, len(self.fields)), dtype=np.int32)

    def postprocess(
        self,
        measurement_folders,
        cpu_array,
    ):
        """Postprocess all relevant folders"""
        mlen = len(measurement_folders)

        # Set the id in the first column
        for index in range(self.data_length):
            self.array[index, 0] = index

        processing_range = min(mlen, self.history)
        column = 1

        # Iterate backwards through the measurement list
        for measurement in range(mlen - 1, mlen - processing_range - 1, -1):

            for index in range(self.data_length):

                # Read user time from the cpu_table
                self.array[index, column] = cpu_array.array[
                    measurement * self.data_length + index, 3
                ]

                # Read system time from the cpu_table
                self.array[index, column + 1] = cpu_array.array[
                    measurement * self.data_length + index, 4
                ]

            column += 2

    def insert_line(self, line, idx):
        """Insert a line into the table"""
        assert len(line) == len(self.fields)
        self.array[idx] = line

    def show(self):
        """Show content with matplotlib"""
        import matplotlib.pyplot as plt

        fig, axis = plt.subplots()

        for i in range(len(self.fields)):
            if i % 2 == 0:
                style = "-o"
            else:
                style = "-x"
            axis.plot(self.array[:, i], style, label=self.fields[i][0])

        plt.legend()
        plt.title("CPU History Stacked  " + self.name)

        plt.show()

    def update_table(self):
        """Create table and prepare loading via json and upload"""
        logging.info("Updating table: %s", self.name)
        self.delete_table()

        schema = []
        for i in range(len(self.fields)):
            schema.append(bigquery.SchemaField(self.fields[i][0], self.fields[i][1]))

        self.job_config = bigquery.LoadJobConfig(schema=schema)

        self.json_data = []

        for i in range(self.data_length):
            line = {}
            for j in range(len(self.fields)):
                line[self.fields[j][0]] = int(self.array[i, j])
            self.json_data.append(line)

        self.upload_table()


class MemoryHistory(MeasurementBase):
    """Class to represent a table of measured memory"""

    def __init__(self, lake, name, data_amount, data_length, client, testmode):
        super().__init__(lake, name, data_amount, data_length, client, testmode)

        self.lake = lake
        self.size = self.size
        self.data_length = data_length
        self.array = np.zeros((self.size, 8), dtype=np.int32)
        self.client = client
        self.row_id = 0

    def scrap_zeros(self, measurement_index):
        """Fill an empty measurement with zeros"""
        for sample in range(self.data_length):

            self.insert_line(
                idx=self.row_id,
                mid=measurement_index,
                sample=sample,
                size=0,
                resident=0,
                shared=0,
                text=0,
                data=0,
            )
            self.row_id += 1

    def scrap_data_collectd(self, thefolder, measurement_index):
        """Read measurement data from collectd exports"""

        if not os.path.exists(thefolder):
            raise SystemError("Folder not existing %s" % thefolder)

        types = ["size", "resident", "shared", "text", "data"]
        db = {"size": {}, "resident": {}, "shared": {}, "text": {}, "data": {}}

        for idx, file in enumerate(types):
            # Iterate through all rrd exports

            myfile = f"gauge-mapper-c8y-{file}.rrd.txt"
            thefile = os.path.join(thefolder, myfile)

            try:
                with open(thefile) as thestats:
                    lines = thestats.readlines()

                    assert len(lines) == self.data_length

                    for index in range(len(lines)):
                        timestamp, utime_str = lines[index].split()
                        if utime_str == "None":
                            utime_str = 0
                        db[file][index] = (timestamp, utime_str)

            except FileNotFoundError as err:
                logging.warning("File not found, skipping for now! %s", str(err))

        for sample in range(self.data_length):
            # Warn if timestamps differ

            size_stamp = int(float(db["size"][sample][0]))
            resident_stamp = int(float(db["resident"][sample][0]))
            shared_stamp = int(float(db["shared"][sample][0]))
            text_stamp = int(float(db["text"][sample][0]))
            data_stamp = int(float(db["data"][sample][0]))

            if (
                not size_stamp
                == resident_stamp
                == shared_stamp
                == text_stamp
                == data_stamp
            ):
                logging.info(
                    "Warning: timestamps differ: %s %s %s %s %s"
                    % (size_stamp, resident_stamp, shared_stamp, text_stamp, data_stamp)
                )

        for sample in range(self.data_length):

            self.insert_line(
                idx=self.row_id,
                mid=measurement_index,
                sample=sample,
                size=int(float(db["size"][sample][1])),
                resident=int(float(db["resident"][sample][1])),
                shared=int(float(db["shared"][sample][1])),
                text=int(float(db["text"][sample][1])),
                data=int(float(db["data"][sample][1])),
            )
            self.row_id += 1

    def scrap_data(self, thefile, measurement_index, arr):
        """Read measurement data from file"""
        with open(thefile) as thestats:
            lines = thestats.readlines()
            sample = 0
            for line in lines:
                entries = line.split()
                size = entries[0]  #     (1) total program size
                resident = entries[1]  #   (2) resident set size
                shared = entries[2]  #     (3) number of resident shared pages
                text = entries[3]  #       (4) text (code)
                # lib = entries[4] #      (5) library (unused since Linux 2.6; always 0)
                data = entries[5]  #      (6) data + stack

                arr.insert_line(
                    idx=self.row_id,
                    mid=measurement_index,
                    sample=sample,
                    size=size,
                    resident=resident,
                    shared=shared,
                    text=text,
                    data=data,
                )
                sample += 1
                self.row_id += 1

        logging.debug("Read %s Memory stats", sample)
        missing = self.data_length - sample
        for miss in range(missing):

            arr.insert_line(
                idx=self.row_id,
                mid=measurement_index,
                sample=sample,
                size=0,
                resident=0,
                shared=0,
                text=0,
                data=0,
            )
            sample += 1
            self.row_id += 1

    def postprocess(self, folders, testname, filename, binary):
        """Postprocess all relevant folders"""
        for folder in folders:
            index = self.foldername_to_index(folder)

            statsfile = (
                f"{self.lake}/{folder}/PySys/{testname}/Output/linux/{filename}.out"
            )

            # Select one of them to check if we measured with collectd
            rrdfile = f"{self.lake}/{folder}/PySys/analytics/{testname}/Output/linux/gauge-mapper-c8y-resident.rrd.txt"
            rrdfolder = f"{self.lake}/{folder}/PySys/analytics/{testname}/Output/linux/"

            # After sorting tests into folders
            rrdfile_old = f"{self.lake}/{folder}/PySys/{testname}/Output/linux/gauge-mapper-c8y-resident.rrd.txt"
            rrdfolder_old = f"{self.lake}/{folder}/PySys/{testname}/Output/linux/"

            if os.path.exists(statsfile):
                self.scrap_data(statsfile, index, self)
            elif os.path.exists(rrdfile):
                self.scrap_data_collectd(rrdfolder, index)
            elif os.path.exists(rrdfile_old):
                self.scrap_data_collectd(rrdfolder_old, index)
            else:
                # breakpoint()
                # raise SystemError("File does not exist !!!")
                logging.info(
                    "Memory analytics does not exist !!! %s or %s"
                    % (statsfile, rrdfile)
                )
                logging.info("Filling with zeros")
                self.scrap_zeros(index)

    def insert_line(self, idx, mid, sample, size, resident, shared, text, data):
        """Insert a line into the table"""
        self.array[idx] = [idx, mid, sample, size, resident, shared, text, data]

    def show(self):
        """Show content with matplotlib"""
        import matplotlib.pyplot as plt

        fig, axis = plt.subplots()
        style = "."
        # ax.plot(self.array[:,0], 'o-')
        axis.plot(self.array[:, 1], style, label="mid")
        axis.plot(self.array[:, 2], style, label="sample")
        axis.plot(self.array[:, 3], style, label="size")
        axis.plot(self.array[:, 4], style, label="resident")
        axis.plot(self.array[:, 5], style, label="shared")
        axis.plot(self.array[:, 6], style, label="text")
        axis.plot(self.array[:, 7], style, label="data")

        plt.legend()
        plt.title("Memory History  " + self.name)

        plt.show()

    # Keep this in case we want real SQL publishing again
    #
    #    def update_table_one_by_one(self, dbo):
    #        for i in range(self.size):
    #            assert self.array[i, 0] == i
    #            q = (
    #                f"insert into {dbo}.{mem_table} values ( {i}, {self.array[i,1]},"
    #                f" {self.array[i,2]}, {self.array[i,3]},{self.array[i,4]},"
    #                f"{self.array[i,5]},{self.array[i,6]}, {self.array[i,7]} );"
    #            )
    #            # print(q)
    #            myquery(self.client, q)

    def update_table(self):
        """Create table and prepare loading via json and upload"""
        self.delete_table()
        logging.info("Updating table: %s", self.name)
        self.job_config = bigquery.LoadJobConfig(
            schema=[
                bigquery.SchemaField("id", "INT64"),
                bigquery.SchemaField("mid", "INT64"),
                bigquery.SchemaField("sample", "INT64"),
                bigquery.SchemaField("size", "INT64"),
                bigquery.SchemaField("resident", "INT64"),
                bigquery.SchemaField("shared", "INT64"),
                bigquery.SchemaField("text", "INT64"),
                bigquery.SchemaField("data", "INT64"),
            ],
        )

        self.json_data = []

        for i in range(self.size):
            self.json_data.append(
                {
                    "id": int(self.array[i, 0]),
                    "mid": int(self.array[i, 1]),
                    "sample": int(self.array[i, 2]),
                    "size": int(self.array[i, 3]),
                    "resident": int(self.array[i, 4]),
                    "shared": int(self.array[i, 5]),
                    "text": int(self.array[i, 6]),
                    "data": int(self.array[i, 6]),
                }
            )

        self.upload_table()
