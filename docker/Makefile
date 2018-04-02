http-shell:
	docker exec -it veda.http /bin/bash

up:
	docker-compose up -d

down:
	docker stop veda.rabbitmq veda.http veda.encode veda.pipeline veda.deliver
	docker rm veda.rabbitmq veda.http veda.encode veda.pipeline veda.deliver
