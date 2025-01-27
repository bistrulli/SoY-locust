Connect to the docker image (postgres):
	 docker exec -it 63821a27da2e bash

Then connect to database:

	psql -lplagedba -dplagedb

Update statemeent and session :

	update plagesession set end_date ='2026-06-17’;
	update studentstatement set deadline_date='2026-06-17’;