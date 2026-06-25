import os
import json
import csv
from unittest import result

import pandas as pd
import numpy as np
from influxdb import InfluxDBClient


def get_from_influxdb(run_id):
    client = InfluxDBClient('lange.xyz', 8086, '', '', 'sou')
    client.switch_database('sou')
    q = 'SELECT "state" FROM "run" WHERE ("runID"::tag = \'' + run_id + '\')'
    result = client.query(q)

    res = {
        "start_time": None,
        "end_time": None,

        "cpu_usage_mean": None,
        "cpu_usage_max": None,
        "cpu_usage_min": None,
        "cpu_usage_std": None,

        "mem_active_mean": None,
        "mem_active_max": None,
        "mem_active_min": None,
        "mem_active_std": None,

        "power_apparent_mean": None,
        "power_apparent_max": None,
        "power_apparent_min": None,
        "power_apparent_std": None,

        "power_total_max": None,
        "power_total_min": None,
        "power_total_diff": None,
    }

    for row in result.get_points():
        if row['state'] == 1.0:
            res["start_time"] = row['time']
        elif row['state'] == 2.0:
            res["end_time"] = row['time']

    if res["start_time"] is not None and res["end_time"] is not None:
        client.switch_database('telegraf')

        q = 'SELECT mean("usage_user"),max("usage_user"),min("usage_user"),stddev("usage_user") FROM "cpu" WHERE ("host"::tag = \'test-ubuntu\' AND "cpu"::tag = \'cpu-total\') AND time >= \'' + \
            res["start_time"] + '\' AND time <= \'' + res["end_time"] + '\'  ORDER BY time ASC'
        result = client.query(q)
        rq = result.get_points().__next__()
        res["cpu_usage_mean"] = rq["mean"]
        res["cpu_usage_max"] = rq["max"]
        res["cpu_usage_min"] = rq["min"]
        res["cpu_usage_std"] = rq["stddev"]

        q = 'SELECT mean("active"),max("active"),min("active"),stddev("active") FROM "mem" WHERE ("host"::tag = \'test-ubuntu\' ) AND time >= \'' + \
            res["start_time"] + '\' AND time <= \'' + res["end_time"] + '\'  ORDER BY time ASC'
        result = client.query(q)
        rq = result.get_points().__next__()
        res["mem_active_mean"] = rq["mean"]
        res["mem_active_max"] = rq["max"]
        res["mem_active_min"] = rq["min"]
        res["mem_active_std"] = rq["stddev"]

        q = 'SELECT mean("ApparentPower"),max("ApparentPower"),min("ApparentPower"),stddev("ApparentPower") FROM "tasmota" WHERE ("topic"::tag = \'tele/tasmota_FA3A6F/SENSOR\' ) AND time >= \'' + \
            res["start_time"] + '\' AND time <= \'' + res["end_time"] + '\'  ORDER BY time ASC'
        result = client.query(q)
        rq = result.get_points().__next__()
        res["power_apparent_mean"] = rq["mean"]
        res["power_apparent_max"] = rq["max"]
        res["power_apparent_min"] = rq["min"]
        res["power_apparent_std"] = rq["stddev"]

        q = 'SELECT max("Total"),min("Total") FROM "tasmota" WHERE ("topic"::tag = \'tele/tasmota_FA3A6F/SENSOR\' ) AND time >= \'' + \
            res["start_time"] + '\' AND time <= \'' + res["end_time"] + '\'  ORDER BY time ASC'
        result = client.query(q)
        rq = result.get_points().__next__()
        res["power_total_max"] = rq["max"]
        res["power_total_min"] = rq["min"]
        res["power_total_diff"] = res["power_total_max"] - res["power_total_min"]

    return res


#dirname = "/Users/benoit/_SOU/results/"
dirname = "/Users/benoit/_SOU/tmp/"
contents = os.listdir(dirname)

results = []
aggregated_results = []

for filename in contents:
    f = os.path.join(dirname, filename) + "/"
    if os.path.isdir(f) and f != "tmp":
        try:
            print("Processed ", f)
            node_data = get_from_influxdb(filename)

            with open(f + 'config.json') as json_data:
                d = json.load(json_data)
                json_data.close()
            errors = {}
            with open(f + 'locust.csv_failures.csv', mode='r', encoding='utf-8') as csvfile:
                csvreader = csv.DictReader(csvfile)
                for row in csvreader:
                    name = row['Name']
                    error = row['Error']
                    nb_errors = row['Occurrences']
                    if name not in errors:
                        errors[name] = {"nb_errors": 0, "errors": ""}
                    errors[name]["nb_errors"] += int(nb_errors)
                    errors[name]["errors"] += error + "___" + nb_errors + "|"

            metrics = {
                "ms-exercise_util_mean": None,
                "ms-exercise_util_min": None,
                "ms-exercise_util_max": None,
                "ms-exercise_util_std": None,
                "ms-exercise_replica_mean": None,
                "ms-exercise_replica_min": None,
                "ms-exercise_replica_max": None,
                "ms-exercise_replica_std": None,

                "ms-other_util_mean": None,
                "ms-other_util_min": None,
                "ms-other_util_max": None,
                "ms-other_util_std": None,
                "ms-other_replica_mean": None,
                "ms-other_replica_min": None,
                "ms-other_replica_max": None,
                "ms-other_replica_std": None,

                "ms-gateway_util_mean": None,
                "ms-gateway_util_min": None,
                "ms-gateway_util_max": None,
                "ms-gateway_util_std": None,
                "ms-gateway_replica_mean": None,
                "ms-gateway_replica_min": None,
                "ms-gateway_replica_max": None,
                "ms-gateway_replica_std": None,
            }
            if os.path.isfile(f + "results/" + 'ms-exercise.csv'):
                tmp = pd.read_csv(f + "results/ms-exercise.csv")
                metrics["ms-exercise_util_mean"] = tmp["util"].mean()
                metrics["ms-exercise_util_min"] = tmp["util"].min()
                metrics["ms-exercise_util_max"] = tmp["util"].max()
                metrics["ms-exercise_util_std"] = tmp["util"].std()
                metrics["ms-exercise_replica_mean"] = tmp["replica"].mean()
                metrics["ms-exercise_replica_min"] = tmp["replica"].min()
                metrics["ms-exercise_replica_max"] = tmp["replica"].max()
                metrics["ms-exercise_replica_std"] = tmp["replica"].std()

            if os.path.isfile(f + "results/" + 'gateway.csv'):
                tmp = pd.read_csv(f + "results/gateway.csv")
                metrics["ms-gateway_util_mean"] = tmp["util"].mean()
                metrics["ms-gateway_util_min"] = tmp["util"].min()
                metrics["ms-gateway_util_max"] = tmp["util"].max()
                metrics["ms-gateway_util_std"] = tmp["util"].std()
                metrics["ms-gateway_replica_mean"] = tmp["replica"].mean()
                metrics["ms-gateway_replica_min"] = tmp["replica"].min()
                metrics["ms-gateway_replica_max"] = tmp["replica"].max()
                metrics["ms-gateway_replica_std"] = tmp["replica"].std()

            if os.path.isfile(f + "results/" + 'ms-other.csv'):
                tmp = pd.read_csv(f + "results/ms-other.csv")
                metrics["ms-other_util_mean"] = tmp["util"].mean()
                metrics["ms-other_util_min"] = tmp["util"].min()
                metrics["ms-other_util_max"] = tmp["util"].max()
                metrics["ms-other_util_std"] = tmp["util"].std()
                metrics["ms-other_replica_mean"] = tmp["replica"].mean()
                metrics["ms-other_replica_min"] = tmp["replica"].min()
                metrics["ms-other_replica_max"] = tmp["replica"].max()
                metrics["ms-other_replica_std"] = tmp["replica"].std()

            with open(f + 'locust.csv_stats.csv', mode='r', encoding='utf-8') as csvfile:
                csvreader = csv.DictReader(csvfile)
                for row in csvreader:
                    name = row['Name']
                    sum_errors = 0
                    errors_logs = ""
                    if name in errors:
                        sum_errors = errors[name]["nb_errors"]
                        errors_logs = errors[name]["errors"]
                    r = {**d, **row, **node_data, **metrics, 'nb_errors': sum_errors, 'errors': errors_logs}
                    if name == 'Aggregated':
                        aggregated_results.append(r)
                    else:
                        results.append(r)

        except Exception as e:
            print("\tError :", f)


class NpEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super(NpEncoder, self).default(obj)


df = pd.read_json(json.dumps(results, cls=NpEncoder))
df.to_csv(dirname + '_res.csv', encoding='utf-8', index=False, sep=';')

df = pd.read_json(json.dumps(aggregated_results, cls=NpEncoder))
df.to_csv(dirname + '_aggregated.csv', encoding='utf-8', index=False, sep=';')

final_results = {}


def generateKey(aggregated_result):
    key = ""
    key += str(aggregated_result["loadshape"])
    key += str(aggregated_result["replicas_g"])
    key += "_" + str(aggregated_result["replicas_e"])
    key += "_" + str(aggregated_result["replicas_o"])
    key += "_" + str(aggregated_result["autoscaler"])
    key += "_" + str(aggregated_result["autoscaler_replicas_g"])
    key += "_" + str(aggregated_result["autoscaler_replicas_e"])
    key += "_" + str(aggregated_result["autoscaler_replicas_o"])
    key += "_" + str(aggregated_result["vu"])
    key += "_" + str(aggregated_result["spawn_rate"])
    key += "_" + str(aggregated_result["bench"])
    key += "_" + str(aggregated_result["prediction_horizon"])
    key += "_" + str(aggregated_result["target_utilization"])
    key += "_" + str(aggregated_result["control_window"])
    key += "_" + str(aggregated_result["estimation_window"])
    key += "_" + str(aggregated_result["measurement_period"])
    return key


for aggregated_result in aggregated_results:
    key = generateKey(aggregated_result)
    if key not in final_results:
        final_results[key] = []
    final_results[key].append(aggregated_result)

final = []


def sum_items(item, param):
    total = 0
    for i in item:
        if i[param] is not None:
            total += float(i[param])
    return total


def mean_items(item, param):
    total = 0
    for i in item:
        if i[param] is not None:
            total += float(i[param])
    return total / len(item)


for final_result in final_results:
    item = final_results[final_result]
    res = {
        "nb_iter": len(item),
        "loadshape":item[0]["loadshape"],
        "replicas_g": item[0]["replicas_g"],
        "replicas_e": item[0]["replicas_e"],
        "replicas_o": item[0]["replicas_o"],
        "autoscaler": item[0]["autoscaler"],
        "autoscaler_replicas_g": item[0]["autoscaler_replicas_g"],
        "autoscaler_replicas_e": item[0]["autoscaler_replicas_e"],
        "autoscaler_replicas_o": item[0]["autoscaler_replicas_o"],
        "vu": item[0]["vu"],
        "spawn_rate": item[0]["spawn_rate"],
        "bench": item[0]["bench"],
        "prediction_horizon": item[0]["prediction_horizon"],
        "target_utilization": item[0]["target_utilization"],
        "control_window": item[0]["control_window"],
        "estimation_window": item[0]["estimation_window"],
        "measurement_period": item[0]["measurement_period"],

        "Request Count": mean_items(item, "Request Count"),
        "Failure Count": mean_items(item, "Failure Count"),

        "Ratio Failure Count": mean_items(item, "Failure Count")/mean_items(item, "Request Count"),

        "Median Response Time": mean_items(item, "Median Response Time"),
        "Average Response Time": mean_items(item, "Average Response Time"),
        "Min Response Time": mean_items(item, "Min Response Time"),
        "Max Response Time": mean_items(item, "Max Response Time"),
        "Average Content Size": mean_items(item, "Average Content Size"),
        "Requests/s": mean_items(item, "Requests/s"),
        "Failures/s": mean_items(item, "Failures/s"),
        "50%": mean_items(item, "50%"),
        "66%": mean_items(item, "66%"),
        "75%": mean_items(item, "75%"),
        "80%": mean_items(item, "80%"),
        "90%": mean_items(item, "90%"),
        "95%": mean_items(item, "95%"),
        "98%": mean_items(item, "98%"),
        "99%": mean_items(item, "99%"),
        "100%": mean_items(item, "100%"),

        "cpu_usage_mean": mean_items(item, "cpu_usage_mean"),
        "cpu_usage_max": mean_items(item, "cpu_usage_max"),
        "cpu_usage_min": mean_items(item, "cpu_usage_min"),
        "cpu_usage_std": mean_items(item, "cpu_usage_std"),
        "mem_active_mean": mean_items(item, "mem_active_mean"),
        "mem_active_max": mean_items(item, "mem_active_max"),
        "mem_active_min": mean_items(item, "mem_active_min"),
        "mem_active_std": mean_items(item, "mem_active_std"),
        "power_apparent_mean": mean_items(item, "power_apparent_mean"),
        "power_apparent_max": mean_items(item, "power_apparent_max"),
        "power_apparent_min": mean_items(item, "power_apparent_min"),
        "power_apparent_std": mean_items(item, "power_apparent_std"),

        "power_total_max": mean_items(item, "power_total_max"),
        "power_total_min": mean_items(item, "power_total_min"),
        "power_total_diff": mean_items(item, "power_total_diff"),

        "ms-exercise_util_mean": mean_items(item, "ms-exercise_util_mean"),
        "ms-exercise_util_min": mean_items(item, "ms-exercise_util_min"),
        "ms-exercise_util_max": mean_items(item, "ms-exercise_util_max"),
        "ms-exercise_util_std": mean_items(item, "ms-exercise_util_std"),
        "ms-exercise_replica_mean": mean_items(item, "ms-exercise_replica_mean"),
        "ms-exercise_replica_min":  mean_items(item, "ms-exercise_replica_min"),
        "ms-exercise_replica_max": mean_items(item, "ms-exercise_replica_max"),
        "ms-exercise_replica_std": mean_items(item, "ms-exercise_replica_std"),
        "ms-other_util_mean": mean_items(item, "ms-other_util_mean"),
        "ms-other_util_min": mean_items(item, "ms-other_util_min"),
        "ms-other_util_max": mean_items(item, "ms-other_util_max"),
        "ms-other_util_std": mean_items(item, "ms-other_util_std"),
        "ms-other_replica_mean": mean_items(item, "ms-other_replica_mean"),
        "ms-other_replica_min": mean_items(item, "ms-other_replica_min"),
        "ms-other_replica_max": mean_items(item, "ms-other_replica_max"),
        "ms-other_replica_std": mean_items(item, "ms-other_replica_std"),
        "ms-gateway_util_mean": mean_items(item, "ms-gateway_util_mean"),
        "ms-gateway_util_min": mean_items(item, "ms-gateway_util_min"),
        "ms-gateway_util_max": mean_items(item, "ms-gateway_util_max"),
        "ms-gateway_util_std": mean_items(item, "ms-gateway_util_std"),
        "ms-gateway_replica_mean": mean_items(item, "ms-gateway_replica_mean"),
        "ms-gateway_replica_min": mean_items(item, "ms-gateway_replica_min"),
        "ms-gateway_replica_max": mean_items(item, "ms-gateway_replica_max"),
        "ms-gateway_replica_std": mean_items(item, "ms-gateway_replica_std"),
        "nb_errors": mean_items(item, "nb_errors")
    }
    final.append(res)

print("Final results :", len(final), dirname + '_final.csv')
df = pd.read_json(json.dumps(final, cls=NpEncoder))
df.to_csv(dirname + '_final.csv', encoding='utf-8', index=False, sep=';')
