import argparse
import logging

import requests

import time

logger = logging.getLogger(__name__)


def write_bdd_logger(
        host="http://lange.xyz:8086",
        bdd="sou",
        run_id="00000000",
        bench="SOU",
        machine="init",
        replicas_g=1,
        replicas_e=1,
        replicas_o=1,
        autoscaler=1,
        autoscaler_replicas_g=1,
        autoscaler_replicas_e=1,
        autoscaler_replicas_o=1,
        vu=200,
        spawn_rate=10,
        run_time=600,
        local_loadshape="linear",
        iteration=0,
        state="init"
):
    tag, url = generate_tags(autoscaler, autoscaler_replicas_e, autoscaler_replicas_g, autoscaler_replicas_o, bdd,
                             bench,
                             host, local_loadshape,iteration, machine, replicas_e, replicas_g, replicas_o, run_id, run_time, spawn_rate,
                             vu, state=state)

    state_value = 0
    if state == "start":
        state_value = 1
    elif state == "stop":
        state_value = 2
    value = {
        "state": state_value,
        "value": 1
    }

    write_to_influx(url, tag, value)


def write_to_influx(url, tag, value):
    data_string = 'run,'

    for key in tag:
        data_string = data_string + key + "=" + str(tag[key]) + ","
    data_string = data_string[:-1]

    data_string = data_string + ' '
    for key in value:
        data_string = data_string + key + "=" + str(value[key]) + ","
    data_string = data_string[:-1]

    logging.info(data_string)

    connect_loop=True
    while connect_loop:
        try:
            res = requests.post(url, data=data_string,timeout=60)
            if res.status_code >= 300:
                print(res)
            connect_loop = False
        except requests.exceptions.RequestException:  # любая ошибка requests
            print('ConnectionError')
            time.sleep(20)
            continue


def generate_tags(autoscaler, autoscaler_replicas_e, autoscaler_replicas_g, autoscaler_replicas_o, bdd, bench, host,local_loadshape,
                  iteration, machine, replicas_e, replicas_g, replicas_o, run_id, run_time, spawn_rate, vu, state):
    url = host + "/write?db=" + bdd
    tag = {
        "state": state,
        "runID": run_id,
        "replicasG": replicas_g,
        "replicasE": replicas_e,
        "replicasO": replicas_o,
        "autoscaler": autoscaler,
        "vu": vu,
        "machine": machine,
        "bench": bench,
        "iteration": iteration,
        "spawn_rate": spawn_rate,
        "run_time": run_time,
        "loadshape": local_loadshape,
        "autoscaler_replicasG": autoscaler_replicas_g,
        "autoscaler_replicasE": autoscaler_replicas_e,
        "autoscaler_replicasO": autoscaler_replicas_o
    }
    return tag, url
