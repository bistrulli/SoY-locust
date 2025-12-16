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
        local_run_time=30):
    for i in range(1):
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
            iteration=i)


if __name__ == "__main__":
    args = xp_runner.utils.parse_arguments()
    #    prediction_horizon = 10
    #    control_window = 20
    # estimation_window=20
    # target_utilization=0.2
    measurement_period = "1s"
    vu = 500
    spawn_rate = 50
    run_time = 300
    start = True
    prediction_horizon=10
#    for prediction_horizon in [10, 20, 30]:
    for control_window in [10, 20, 30]:
        estimation_window = control_window
        for target_utilization in [0.2, 0.4, 0.6, 0.8]:
            print("prediction_horizon", prediction_horizon)
            print("control_window", control_window)
            print("estimation_window", estimation_window)
            print("target_utilization", target_utilization)
            print("========================================")
            if start:
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
                    local_run_time=run_time)

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
                    local_run_time=run_time)

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
                    local_run_time=run_time)

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
                    local_run_time=run_time)

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
                    local_run_time=run_time)
