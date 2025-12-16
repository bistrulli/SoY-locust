#!/bin/bash



bench="SOU_NO_AUTO_SCALE"
machine="192.168.3.102"
docker_engine=$machine
docker_engine_port=2375


stack="sou/monotloth-v5.yml"
locust_file="./test.py"

vu=200
spaw_rate=10
run_time="5m"





run_test() {
	END=1
  step="init"
	$("python3 _write-Influx.py --runID $1 --bench=$2 --machine=$3 --replicasG=$4 --replicasE=$5 --replicasO=$6 --autoscaler=$7 --vu=$11 --step=$step")
	for i in $(seq 1 $END); do
		$("DOCKER_HOST=tcp://$docker_engine:$docker_engine_port docker stack deploy --compose-file $stack ms-stack-v5")
		sleep 25s
		#Scale services
		$("DOCKER_HOST=tcp://$docker_engine:$docker_engine_port docker service scale ms-stack-v5_gateway=$4")
		$("DOCKER_HOST=tcp://$docker_engine:$docker_engine_port docker service scale ms-stack-v5_ms-exercise=$5")
		$("DOCKER_HOST=tcp://$docker_engine:$docker_engine_port docker service scale ms-stack-v5_ms-other=$6")
		$("DOCKER_HOST=tcp://$docker_engine:$docker_engine_port docker service scale ms-stack-v5_auto-scaler=$7")
		sleep 15s
		if ${8};
		then
		  $("python3 _autoscaler-write-config.py --service-name=gateway")
		  $("python3 _autoscaler-start.py --service-name=gateway")
    fi
		if ${9};
		then
		  $("python3 _autoscaler-write-config.py --service-name=ms-exercise")
		  $("python3 _autoscaler-start.py --service-name=ms-exercise")
    fi
    if ${10};
    then
      $("python3 _autoscaler-write-config.py --service-name=ms-other")
      $("python3 _autoscaler-start.py --service-name=ms-other")
    fi
		# Launch locust test
		step="start"
		echo "      $step $i" >&2
		$("python3 _write-Influx.py --runID=$1 --bench=$2 --machine=$3 --replicasG=$4 --replicasE=$5 --replicasO=$6  --autoscaler=$7 --vu=$11  --step=$step --iteration=$i")
		####$("python3 debug_locust.py --spawn-rate 10 --host http://$machine --locust-file $8 --loadshape-file $loadshape_file")
		step="stop"
		echo "      $step $i" >&2
		$("python3 _write-Influx.py --runID=$1 --bench=$2 --machine=$3 --replicasG=$4 --replicasE=$5 --replicasO=$6  --autoscaler=$7 --vu=$11 --step=$step --iteration=$i")
		if ${8};
    then
      $("python3 _autoscaler-stop.py --service-name=gateway")
    fi
    if ${9};
    then
      $("python3 _autoscaler-stop.py --service-name=ms-exercise")
    fi
    if ${10};
    then
      $("python3 _autoscaler-stop.py --service-name=ms-other")
    fi
		$("DOCKER_HOST=tcp://$docker_engine:$docker_engine_port stack rm ms-stack-v5")
		sleep 25s
	done
	step="init"
	$("python3 _write-Influx.py --runID=$1 --bench=$2 --machine=$3 --replicasG=$4 --replicasE=$5 --replicasO=$6  --autoscaler=$7 --vu=$11  --step=$step")
}








#uuid=$(cat /proc/sys/kernel/random/uuid)
uuid="dsqdsqdsqdqs"



replicasG=1
replicasE=1
replicasO=1
autoscaler=0
autoscalerReplicasG=true
autoscalerReplicasE=true
autoscalerReplicasO=true


run_test $uuid $bench $machine $replicasG $replicasE $replicasO $autoscaler $autoscalerReplicasG $autoscalerReplicasE $autoscalerReplicasO $vu
