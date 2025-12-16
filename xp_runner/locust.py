import logging
import subprocess
logger = logging.getLogger(__name__)


def execute_locust_test(
        users=200,
        spawn_rate=10,
        run_time=600,
        host="http://192.168.3.102:80",
        log_level="INFO",
        csv_base="results/SoyMonoShorterIfLogin_x6/SoyMonoShorterIfLogin_x6.csv",
        log_file="results/SoyMonoShorterIfLogin_x6/SoyMonoShorterIfLogin_x6.log",
        locust_file="test.py"
):
    cmd = ["locust", "--headless",
           "--u", str(users),
           "--spawn-rate", str(spawn_rate),
           "--run-time", str(run_time),
           "--host", host,
           "--csv", csv_base,
           "--loglevel", log_level,
           "--logfile", log_file,
           "-f", locust_file]
    print("Executing command:")
    print(' '.join(cmd))
    subprocess.run(cmd,  capture_output=True, text=True)
    print("Locust completed successfully")

