import argparse
import logging
import os
import subprocess
import time
import json

import xp_runner

logger = logging.getLogger(__name__)


def parse_arguments():
    parser = argparse.ArgumentParser()

    parser.add_argument("--host", default="http://lange.xyz:8086",
                        help="URL du serveur orchestrateur")

    parser.add_argument("--stack-name", default="ms-stack-v5")
    parser.add_argument("--docker-compose-config", default="sou/monotloth-v5.yml")

    parser.add_argument("--prom-host", default="192.168.3.102")
    parser.add_argument("--prom-port", type=int, default=9090)

    parser.add_argument("--remote-docker-host", default="192.168.3.102")
    parser.add_argument("--remote-docker-port", type=int, default=2375)

    args = parser.parse_args()
    return args


def generate_res_folder():
    dirname = "results/tmp/"
    if not os.path.exists(dirname):
        os.makedirs(dirname)
    return dirname


def scale_services(stack_name="ms-stack-v5",
                   nb_replicas_ms_exercise=1, nb_replicas_ms_other=1, nb_replicas_ms_gateway=1,
                   nb_replicas_auto_scaler=1,
                   remote_docker_host=None, remote_docker_port=2375):
    xp_runner.docker_sou.scale_service(
        service_name="ms-exercise",
        stack_name=stack_name,
        replicas=nb_replicas_ms_exercise,
        remote_docker_host=remote_docker_host,
        remote_docker_port=remote_docker_port
    )

    xp_runner.docker_sou.scale_service(
        service_name="ms-other",
        stack_name=stack_name,
        replicas=nb_replicas_ms_other,
        remote_docker_host=remote_docker_host,
        remote_docker_port=remote_docker_port
    )
    xp_runner.docker_sou.scale_service(
        service_name="gateway",
        stack_name=stack_name,
        replicas=nb_replicas_ms_gateway,
        remote_docker_host=remote_docker_host,
        remote_docker_port=remote_docker_port
    )
    xp_runner.docker_sou.scale_service(
        service_name="auto-scaler",
        stack_name=stack_name,
        replicas=nb_replicas_auto_scaler,
        remote_docker_host=remote_docker_host,
        remote_docker_port=remote_docker_port
    )


def configure_autoscaler(
        prediction_horizon=10,
        target_utilization=0.2,
        control_window=20,
        estimation_window=20,
        measurement_period="1s",
        ms_exercice=False, ms_other=False, ms_gateway=False,
        remote_docker_host=None, remote_docker_port=2375):
    if ms_exercice:
        xp_runner.autoscaller.configure_autoscaler(
            prediction_horizon=prediction_horizon,
            target_utilization=target_utilization,
            control_window=control_window,
            estimation_window=estimation_window,
            measurement_period=measurement_period,
            service_name="ms-exercise",
            remote_docker_host=remote_docker_host,
            remote_docker_port=remote_docker_port)
    if ms_other:
        xp_runner.autoscaller.configure_autoscaler(prediction_horizon=prediction_horizon,
                                                   target_utilization=target_utilization,
                                                   control_window=control_window,
                                                   estimation_window=estimation_window,
                                                   measurement_period=measurement_period,
                                                   service_name="ms-other",
                                                   remote_docker_host=remote_docker_host,
                                                   remote_docker_port=remote_docker_port)
    if ms_gateway:
        xp_runner.autoscaller.configure_autoscaler(prediction_horizon=prediction_horizon,
                                                   target_utilization=target_utilization,
                                                   control_window=control_window,
                                                   estimation_window=estimation_window,
                                                   measurement_period=measurement_period,
                                                   service_name="gateway",
                                                   remote_docker_host=remote_docker_host,
                                                   remote_docker_port=remote_docker_port)


def start_autoscaler(ms_exercice=False, ms_other=False, ms_gateway=False):
    if ms_exercice:
        xp_runner.autoscaller.start_autoscaler(service_name="ms-exercise")
    if ms_other:
        xp_runner.autoscaller.start_autoscaler(service_name="ms-other")
    if ms_gateway:
        xp_runner.autoscaller.start_autoscaler(service_name="gateway")


def stop_autoscaler(ms_exercice=False, ms_other=False, ms_gateway=False):
    if ms_exercice:
        xp_runner.autoscaller.stop_autoscaler(service_name="ms-exercise")
    if ms_other:
        xp_runner.autoscaller.stop_autoscaler(service_name="ms-other")
    if ms_gateway:
        xp_runner.autoscaller.stop_autoscaler(service_name="gateway")


def write_config(dirname="results/tmp",
                 local_replicas_g=1,
                 local_replicas_e=1,
                 local_replicas_o=1,
                 local_autoscaler=1,
                 local_autoscaler_replicas_g=True,
                 local_autoscaler_replicas_e=True,
                 local_autoscaler_replicas_o=True,
                 local_vu=200,
                 local_spawn_rate=200,
                 local_run_time=600,
                 local_run_id="00000000",
                 local_bench="SOU",
                 local_prediction_horizon=10,
                 local_target_utilization=0.2,
                 local_control_window=20,
                 local_estimation_window=20,
                 local_measurement_period="1s",
                 local_iteration=0):
    config_file = dirname.rstrip() + "config.json"
    config = {
        "replicas_g": local_replicas_g,
        "replicas_e": local_replicas_e,
        "replicas_o": local_replicas_o,
        "autoscaler": local_autoscaler,
        "autoscaler_replicas_g": local_autoscaler_replicas_g,
        "autoscaler_replicas_e": local_autoscaler_replicas_e,
        "autoscaler_replicas_o": local_autoscaler_replicas_o,
        "vu": local_vu,
        "spawn_rate": local_spawn_rate,
        "run_time": local_run_time,
        "run_id": local_run_id,
        "bench": local_bench,
        "prediction_horizon": local_prediction_horizon,
        "target_utilization": local_target_utilization,
        "control_window": local_control_window,
        "estimation_window": local_estimation_window,
        "measurement_period": local_measurement_period,
        "iteration": local_iteration
    }
    print("Writing config file: {}".format(config))
    with open(config_file, "w") as f:
        json.dump(config, f, indent=4)
    logger.info(f"Configuration written to {config_file}")


def run_one_shot(
        args,
        replicas_g=1,
        replicas_e=1,
        replicas_o=1,
        autoscaler=1,
        autoscaler_replicas_g=True,
        autoscaler_replicas_e=True,
        autoscaler_replicas_o=True,
        prediction_horizon=10,
        target_utilization=0.2,
        control_window=20,
        estimation_window=20,
        measurement_period="1s",
        vu=200,
        spawn_rate=10,
        run_time=600,
        run_id="00000000",
        bench="SOU",
        iteration=0):
    xp_runner.influx.write_bdd_logger(replicas_o=replicas_o, replicas_e=replicas_e, replicas_g=replicas_g,
                                      autoscaler=autoscaler,
                                      autoscaler_replicas_e=autoscaler_replicas_e,
                                      autoscaler_replicas_g=autoscaler_replicas_g,
                                      autoscaler_replicas_o=autoscaler_replicas_o,
                                      vu=vu, spawn_rate=spawn_rate, run_time=run_time, bench=bench, iteration=iteration,
                                      run_id=run_id, state="init")

    dirname = xp_runner.utils.generate_res_folder()
    xp_runner.utils.write_config(dirname,
                                 local_replicas_o=replicas_o, local_replicas_e=replicas_e, local_replicas_g=replicas_g,
                                 local_autoscaler=autoscaler,
                                 local_autoscaler_replicas_e=autoscaler_replicas_e,
                                 local_autoscaler_replicas_g=autoscaler_replicas_g,
                                 local_autoscaler_replicas_o=autoscaler_replicas_o,
                                 local_vu=vu, local_spawn_rate=spawn_rate, local_run_time=run_time, local_bench=bench, local_iteration=iteration,
                                 local_run_id=run_id)
    if True:
        xp_runner.docker_sou.deploy_stack(
            stack_name=args.stack_name,
            docker_compose_config=args.docker_compose_config,
            remote_docker_host=args.remote_docker_host,
            remote_docker_port=args.remote_docker_port,
        )
        xp_runner.influx.write_bdd_logger(replicas_o=replicas_o, replicas_e=replicas_e, replicas_g=replicas_g,
                                          autoscaler=autoscaler,
                                          autoscaler_replicas_e=autoscaler_replicas_e,
                                          autoscaler_replicas_g=autoscaler_replicas_g,
                                          autoscaler_replicas_o=autoscaler_replicas_o,
                                          vu=vu, spawn_rate=spawn_rate, run_time=run_time, bench=bench, iteration=iteration,
                                          run_id=run_id, state="deploy")

        scale_services(stack_name=args.stack_name,
                       nb_replicas_ms_exercise=replicas_e,
                       nb_replicas_ms_other=replicas_o,
                       nb_replicas_ms_gateway=replicas_g,
                       nb_replicas_auto_scaler=autoscaler,
                       remote_docker_host=args.remote_docker_host,
                       remote_docker_port=args.remote_docker_port)

        xp_runner.influx.write_bdd_logger(replicas_o=replicas_o, replicas_e=replicas_e, replicas_g=replicas_g,
                                          autoscaler=autoscaler,
                                          autoscaler_replicas_e=autoscaler_replicas_e,
                                          autoscaler_replicas_g=autoscaler_replicas_g,
                                          autoscaler_replicas_o=autoscaler_replicas_o,
                                          vu=vu, spawn_rate=spawn_rate, run_time=run_time, bench=bench, iteration=iteration,
                                          run_id=run_id, state="autoscaler_starting")
        configure_autoscaler(prediction_horizon=prediction_horizon,
                             target_utilization=target_utilization,
                             control_window=control_window,
                             estimation_window=estimation_window,
                             measurement_period=measurement_period,
                             ms_exercice=autoscaler_replicas_e, ms_other=autoscaler_replicas_o,
                             ms_gateway=autoscaler_replicas_g, remote_docker_host=args.remote_docker_host,
                             remote_docker_port=args.remote_docker_port)

        start_autoscaler(ms_exercice=autoscaler_replicas_e, ms_other=autoscaler_replicas_o,
                         ms_gateway=autoscaler_replicas_g)

        xp_runner.influx.write_bdd_logger(replicas_o=replicas_o, replicas_e=replicas_e, replicas_g=replicas_g,
                                          autoscaler=autoscaler,
                                          autoscaler_replicas_e=autoscaler_replicas_e,
                                          autoscaler_replicas_g=autoscaler_replicas_g,
                                          autoscaler_replicas_o=autoscaler_replicas_o,
                                          vu=vu, spawn_rate=spawn_rate, run_time=run_time, bench=bench, iteration=iteration,
                                          run_id=run_id, state="start")

        time.sleep(20)
        xp_runner.locust.execute_locust_test(
            users=vu,
            spawn_rate=spawn_rate,
            run_time=run_time,
            csv_base=dirname.rstrip() + "locust.csv",
            log_file=dirname.rstrip() + "locust.log"
        )

        xp_runner.influx.write_bdd_logger(replicas_o=replicas_o, replicas_e=replicas_e, replicas_g=replicas_g,
                                          autoscaler=autoscaler,
                                          autoscaler_replicas_e=autoscaler_replicas_e,
                                          autoscaler_replicas_g=autoscaler_replicas_g,
                                          autoscaler_replicas_o=autoscaler_replicas_o,
                                          vu=vu, spawn_rate=spawn_rate, run_time=run_time, bench=bench, iteration=iteration,
                                          run_id=run_id, state="stop")
        stop_autoscaler(ms_exercice=autoscaler_replicas_e, ms_other=autoscaler_replicas_o, ms_gateway=autoscaler_replicas_g)

        time.sleep(30)  # wait for logs to be written

        xp_runner.docker_sou.cp_stack_logs(
            result_folder=dirname,
            stack_name=args.stack_name,
            remote_docker_host=args.remote_docker_host,
            remote_docker_port=args.remote_docker_port)

        xp_runner.influx.write_bdd_logger(replicas_o=replicas_o, replicas_e=replicas_e, replicas_g=replicas_g,
                                          autoscaler=autoscaler,
                                          autoscaler_replicas_e=autoscaler_replicas_e,
                                          autoscaler_replicas_g=autoscaler_replicas_g,
                                          autoscaler_replicas_o=autoscaler_replicas_o,
                                          vu=vu, spawn_rate=spawn_rate, run_time=run_time, bench=bench, iteration=iteration,
                                          run_id=run_id, state="autoscaler_stopped")

        xp_runner.docker_sou.remove_stack(stack_name=args.stack_name,
                                          remote_docker_host=args.remote_docker_host,
                                          remote_docker_port=args.remote_docker_port)
        xp_runner.influx.write_bdd_logger(replicas_o=replicas_o, replicas_e=replicas_e, replicas_g=replicas_g,
                                          autoscaler=autoscaler,
                                          autoscaler_replicas_e=autoscaler_replicas_e,
                                          autoscaler_replicas_g=autoscaler_replicas_g,
                                          autoscaler_replicas_o=autoscaler_replicas_o,
                                          vu=vu, spawn_rate=spawn_rate, run_time=run_time, bench=bench, iteration=iteration,
                                          run_id=run_id, state="stack_removed")
        logger.info("One-shot run completed.")
    cmd=["mv", dirname.rstrip(), "results/" + str(run_id)]
    subprocess.run(cmd)
    print("Moved results to results/" + str(run_id))
    time.sleep(30)  # wait for logs to be written
