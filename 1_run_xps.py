import xp_runner
import uuid


def run_xps(
        args,
        bench="SOU",
        replicas_g=1,
        replicas_e=1,
        replicas_o=1,
        autoscaler=1,
        autoscaler_replicas_g=True,
        autoscaler_replicas_e=True,
        autoscaler_replicas_o=True,
        local_prediction_horizon=10,
        local_target_utilization=0.2,
        local_control_window=20,
        local_estimation_window=20,
        local_measurement_period="1s",
        local_vu=200,
        local_spawn_rate=50,
        local_run_time=30,
        local_loadshape="linear",
        iterations=1):
    run_id = uuid.uuid4()
    xp_runner.utils.run_one_shot(
        run_id=str(run_id),
        args=args,
        bench=bench,
        replicas_g=replicas_g,
        replicas_e=replicas_e,
        replicas_o=replicas_o,
        autoscaler=autoscaler,
        autoscaler_replicas_g=autoscaler_replicas_g,
        autoscaler_replicas_e=autoscaler_replicas_e,
        autoscaler_replicas_o=autoscaler_replicas_o,
        prediction_horizon=local_prediction_horizon,
        target_utilization=local_target_utilization,
        control_window=local_control_window,
        estimation_window=local_estimation_window,
        measurement_period=local_measurement_period,
        vu=local_vu,
        spawn_rate=local_spawn_rate,
        run_time=local_run_time,
        loadshape=local_loadshape,
        iteration=iterations)


if __name__ == "__main__":
    args = xp_runner.utils.parse_arguments()
    measurement_period = "1s"
    vu = 8000
    spawn_rate = 100
    run_time = 600
#    run_time = 86400
    start = True
    loadshape="twitter2"
#    n = 4
#    prediction_horizons = [10, 20, 30]
#    control_windows = [10, 20, 30]
#    target_utilizations = [0.2, 0.4, 0.6, 0.8]
    n = 1
    prediction_horizons = [10, 20, 30, 40, 50]
    control_windows = [10]
    target_utilizations = [0.3]

    xp_1_1_1_0 = True
    xp_1_8_1_0 = True
    xp_2_8_2_0 = True
    xp_as_1_1_1_1 = True
    xp_as_1_1_1_1_all = True

    for i in range(n):
        for prediction_horizon in prediction_horizons:
            for control_window in control_windows:
                for target_utilization in target_utilizations:

                    estimation_window = control_window
                    print("prediction_horizon", prediction_horizon)
                    print("control_window", control_window)
                    print("estimation_window", estimation_window)
                    print("target_utilization", target_utilization)
                    print("========================================")
                    if start:
                        if xp_1_1_1_0:
                            run_xps(
                                args=args,
                                bench="SOU",
                                replicas_g=1,
                                replicas_e=1,
                                replicas_o=1,
                                autoscaler=0,
                                autoscaler_replicas_g=False,
                                autoscaler_replicas_e=False,
                                autoscaler_replicas_o=False,
                                local_prediction_horizon=prediction_horizon,
                                local_target_utilization=target_utilization,
                                local_control_window=control_window,
                                local_estimation_window=estimation_window,
                                local_measurement_period=measurement_period,
                                local_vu=vu,
                                local_spawn_rate=spawn_rate,
                                local_run_time=run_time,
                                local_loadshape=loadshape,
                                iterations=i)
                        if xp_1_8_1_0:
                            run_xps(
                                args=args,
                                bench="SOU",
                                replicas_g=1,
                                replicas_e=8,
                                replicas_o=1,
                                autoscaler=0,
                                autoscaler_replicas_g=False,
                                autoscaler_replicas_e=False,
                                autoscaler_replicas_o=False,
                                local_prediction_horizon=prediction_horizon,

                                local_target_utilization=target_utilization,
                                local_control_window=control_window,
                                local_estimation_window=estimation_window,
                                local_measurement_period=measurement_period,
                                local_vu=vu,
                                local_spawn_rate=spawn_rate,
                                local_run_time=run_time,
                                local_loadshape=loadshape,
                                iterations=i)
                        if xp_2_8_2_0:
                            run_xps(
                                args=args,
                                bench="SOU",
                                replicas_g=2,
                                replicas_e=8,
                                replicas_o=2,
                                autoscaler=0,
                                autoscaler_replicas_g=False,
                                autoscaler_replicas_e=False,
                                autoscaler_replicas_o=False,
                                local_prediction_horizon=prediction_horizon,
                                local_target_utilization=target_utilization,
                                local_control_window=control_window,
                                local_estimation_window=estimation_window,
                                local_measurement_period=measurement_period,
                                local_vu=vu,
                                local_spawn_rate=spawn_rate,
                                local_run_time=run_time,
                                local_loadshape=loadshape,
                                iterations=i)
                        if xp_as_1_1_1_1:
                            run_xps(
                                args=args,
                                bench="SOU",
                                replicas_g=1,
                                replicas_e=1,
                                replicas_o=1,
                                autoscaler=1,
                                autoscaler_replicas_g=False,
                                autoscaler_replicas_e=True,
                                autoscaler_replicas_o=False,
                                local_prediction_horizon=prediction_horizon,
                                local_target_utilization=target_utilization,
                                local_control_window=control_window,
                                local_estimation_window=estimation_window,
                                local_measurement_period=measurement_period,
                                local_vu=vu,
                                local_spawn_rate=spawn_rate,
                                local_run_time=run_time,
                                local_loadshape=loadshape,
                                iterations=i)
                        if xp_as_1_1_1_1_all:
                            run_xps(
                                args=args,
                                bench="SOU",
                                replicas_g=1,
                                replicas_e=1,
                                replicas_o=1,
                                autoscaler=1,
                                autoscaler_replicas_g=True,
                                autoscaler_replicas_e=True,
                                autoscaler_replicas_o=True,
                                local_prediction_horizon=prediction_horizon,
                                local_target_utilization=target_utilization,
                                local_control_window=control_window,
                                local_estimation_window=estimation_window,
                                local_measurement_period=measurement_period,
                                local_vu=vu,
                                local_spawn_rate=spawn_rate,
                                local_run_time=run_time,
                                local_loadshape=loadshape,
                                iterations=i)
