#!/bin/bash


rsync -r  lange.xyz:~/Soy-locust/ .

rm -rf results/

python3 1_run_xps.py
