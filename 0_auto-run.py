#!/usr/bin/env python3

import logging
import sys

from controller import ControlLoop
from flask import Flask, request, jsonify
import threading

app = Flask(__name__)

logger = logging.getLogger(__name__)

ctrlLoop_gateway = None

controllers = {}

'''
curl -X POST http://192.168.3.102:8081/controllers \
  -H "Content-Type: application/json" \
  -d '{
    "service_name": "ms-other",
    "stack_name": "ms-stack-v5",
    "sysfile": "sou/monotloth-v5.yml",
    "control_window": 60,
    "estimation_window": 60,
    "measurement_period": "1s",
    "outfile": "results/ms-exercise.csv",
    "prediction_horizon": 10,
    "target_utilization": 0.2,
    "disable_prometheus": false,
    "prom_host": "192.168.3.102",
    "prom_port": 9090,
    "remote_docker_host": "192.168.3.102",
    "remote_docker_port": 2375
}'

'''


@app.route("/controllers", methods=["POST"])
def create_controller():
    data = request.get_json(force=True) or {}
    service_name = data.get("service_name")

    if not service_name:
        return jsonify({"error": "service_name is required"}), 400

    config = data

    if service_name in controllers:
        stop_event = controllers[service_name]["stop_event"]
        thread = controllers[service_name]["thread"]
        logger.info("Update of the controller configuration '%s'", service_name)
    else:
        stop_event = threading.Event()
        thread = None
        logger.info("Creation of a new controller '%s'", service_name)

    controllers[service_name] = {
        "config": config,
        "stop_event": stop_event,
        "thread": thread,
        "controller_instance": ControlLoop(config=config)
    }

    return jsonify({"status": "created", "service_name": service_name, "config": config}), 201


@app.route("/controllers/<service_name>/start", methods=["GET"])
def start_controller(service_name):
    global controllers

    if service_name not in controllers:
        return jsonify({"error": f"controller '{service_name}' not found"}), 404

    ctrl = controllers[service_name]
    stop_event = ctrl["stop_event"]
    thread = ctrl["thread"]

    if thread is not None and thread.is_alive():
        logger.info("Loop already in progress for '%s', not restarting", service_name)
        return jsonify({"status": "already running", "service_name": service_name}), 409

    stop_event.clear()

    def runner():
        logger.info("Thread loop_gateway démarré pour '%s'", service_name)
        try:
            ctrl["controller_instance"].loop(stop_event=stop_event)
        except Exception:
            logger.exception("Erreur dans ctrlLoop_gateway.loop() pour '%s'", service_name)
        finally:
            logger.info("Thread loop_gateway terminé pour '%s'", service_name)

    thread = threading.Thread(target=runner, daemon=True)
    ctrl["thread"] = thread
    thread.start()

    logger.info("Thread created for '%s', handing over to the client.", service_name)
    return jsonify({"status": "started", "service_name": service_name})


@app.route("/controllers/<service_name>/stop", methods=["GET"])
def stop_controller(service_name):
    if service_name not in controllers:
        return jsonify({"error": f"controller '{service_name}' not found"}), 404

    ctrl = controllers[service_name]
    thread = ctrl["thread"]
    stop_event = ctrl["stop_event"]

    if thread is None or not thread.is_alive():
        return jsonify({"status": "not running", "service_name": service_name}), 404

    logger.info("Request /stop for '%s'", service_name)

    stop_event.set()
    thread.join(timeout=2.0)

    try:

        ctrl["controller_instance"].saveResults(service_name)
    except Exception:
        logger.exception("Erreur dans saveResults() pour '%s'", service_name)

    return jsonify({"status": "stopping", "service_name": service_name})


@app.route("/controllers/stop_all", methods=["GET"])
def stop_all_controllers():
    logger.info("Request /stop_all received")

    for service_name, ctrl in controllers.items():
        thread = ctrl["thread"]
        stop_event = ctrl["stop_event"]

        if thread is None or not thread.is_alive():
            continue

        logger.info("Request for stop for '%s'", service_name)
        stop_event.set()

    for service_name, ctrl in controllers.items():
        thread = ctrl["thread"]
        c = ctrl["controller_instance"]
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)
            try:
                c.saveResults()
            except Exception:
                logger.exception("Error in saveResults() for '%s'", service_name)

    return jsonify({"status": "all stopping"})


@app.route("/controllers", methods=["GET"])
def list_controllers():
    res = []
    for service_name, ctrl in controllers.items():
        thread = ctrl["thread"]
        running = thread is not None and thread.is_alive()
        res.append({
            "service_name": service_name,
            "running": running,
            "has_config": ctrl["config"] is not None,

        })
    return jsonify(res)


if __name__ == "__main__":
    logging.basicConfig(filename="logs/scheduler.log", level=getattr(logging, "INFO"))
    # logging.basicConfig( level=getattr(logging, "INFO"),stream=sys.stdout)
    app.run(port=8081, host='0.0.0.0', debug=False, threaded=True)
