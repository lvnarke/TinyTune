.PHONY: up down reset logs ps demo smoke saturation python-load scale-api scale-workers baseline optimized benchmark-baseline benchmark-scaled package verify-web verify-google

up:
	docker compose up --build -d

down:
	docker compose down

reset:
	docker compose down -v --remove-orphans

logs:
	docker compose logs -f api worker gateway

ps:
	docker compose ps

demo:
	docker compose --profile load run --rm --no-deps loadgen python scripts/demo.py

smoke:
	STEP_RATES=5,10 STEP_DURATION_SECONDS=3 RUN_LABEL=smoke docker compose --profile load run --rm --no-deps k6

saturation:
	docker compose --profile load run --rm --no-deps k6

python-load:
	docker compose --profile load run --rm --no-deps loadgen

scale-api:
	docker compose up -d --scale api=3

scale-workers:
	docker compose up -d --scale worker=4

baseline:
	CACHE_ENABLED=false PLAY_MODE=sync docker compose up -d --force-recreate --scale api=1 --scale worker=1 api worker

optimized:
	CACHE_ENABLED=true PLAY_MODE=async docker compose up -d --force-recreate api worker

benchmark-baseline:
	$(MAKE) baseline
	STEP_RATES=50,100,200,400,600,800 STEP_DURATION_SECONDS=5 RUN_LABEL=baseline-k6 $(MAKE) saturation

benchmark-scaled:
	$(MAKE) optimized
	docker compose up -d --scale api=3 --scale worker=4
	STEP_RATES=1600,1800,2000,2200,2400 STEP_DURATION_SECONDS=10 RUN_LABEL=optimized-scaled-k6 $(MAKE) saturation

package:
	@archive_dir=$$(mktemp -d); cd .. && zip -rq "$$archive_dir/tinytune.zip" tinytune -x 'tinytune/.env' 'tinytune/*.zip' '*/__pycache__/*' && mv "$$archive_dir/tinytune.zip" tinytune-distributed-system.zip && rmdir "$$archive_dir"

verify-web:
	docker compose --profile load run --rm --no-deps --build loadgen python -m scripts.verify_permissions

verify-google:
	docker compose --profile load run --rm --no-deps --build loadgen python -m scripts.verify_google

