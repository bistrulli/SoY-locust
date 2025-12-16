#!/bin/bash

docker build . -t registry.gitlab.com/inria-mpl/soy/auto-scaler:1.0.0
docker push registry.gitlab.com/inria-mpl/soy/auto-scaler:1.0.0
