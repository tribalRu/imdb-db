#!/bin/bash
# start tmux session with all dev processes

SESSION_NAME="imdb"

wait_for_pg() {
    echo "Waiting for Postgres container to start..."
    while [ "$(docker inspect -f '{{.State.Running}}' imdb-postgres)" != "true" ]; do
        echo "Postgres not running yet, checking again in 5 seconds..."
        sleep 5
    done
    echo "Postgres is running!"
}

cleanup() {
    echo "Cleaning up..."
    docker compose down
    echo "Containers stopped and removed!"
}

trap cleanup EXIT

tmux has-session -t $SESSION_NAME 2>/dev/null

if [ $? != 0 ]; then

    # compose
    tmux new-session -d -s $SESSION_NAME -n "dev"
    tmux send-keys -t $SESSION_NAME:"dev" "docker compose pull imdb-postgres && docker compose up -d imdb-postgres && docker compose logs -f" C-m
    wait_for_pg

    # fastapi
    tmux split-window -t $SESSION_NAME -h
    tmux send-keys -t $SESSION_NAME:"dev.1" "source .venv/bin/activate && cd backend/app && fastapi dev main.py" C-m

    # shell
    tmux split-window -v -t $SESSION_NAME:"dev.0" -l 50%
    tmux send-keys -t $SESSION_NAME:"dev.2" "source .venv/bin/activate && cd backend/app && ipython -i -c 'from main import *'" C-m

    # frontend
    tmux split-window -v -t $SESSION_NAME:"dev.2" -l 50%
    tmux send-keys -t $SESSION_NAME:"dev.3" "source .venv/bin/activate && cd frontend && npm run dev" C-m

fi

tmux attach-session -t $SESSION_NAME
