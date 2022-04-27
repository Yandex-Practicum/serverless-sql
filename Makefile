build_local:
	docker build -f Dockerfile -t local/serverless-sql:latest ./

run_local:
	docker run -e TIMEOUT=30 -e PORT=9999 -p 9999:9999 --rm local/serverless-sql:latest python3 /agent/launch.py
