# Time Keeper

A small time tracking app with an Angular frontend and a Python REST API.

## Run with Docker Compose

From this directory, start both services:

```bash
docker compose up --build
```

Open [http://localhost:8080](http://localhost:8080). Compose stores the SQLite database in the `timekeeper-data` named volume. Stop the services with `docker compose down`; the data volume remains. To remove the database too, run `docker compose down --volumes`.

## API

The API is served through the frontend at `http://localhost:8080/api` (Swagger docs at `/docs` on the backend container).

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Health check |
| `GET` | `/api/tasks` | List tasks and total tracked time |
| `POST` | `/api/tasks` | Create a task (`name`, optional `notes`) |
| `DELETE` | `/api/tasks/{task_id}` | Delete a task and its sessions |
| `GET` | `/api/sessions?task_id={id}` | List time sessions, optionally for a task |
| `POST` | `/api/tasks/{task_id}/start` | Start the timer for a task |
| `POST` | `/api/sessions/{session_id}/stop` | Stop a running timer |

Only one timer can run at a time. Task and session times are stored in UTC.

## Run locally without Docker

Backend:

```bash
cd backend
python -m venv .venv
# Activate the virtual environment, then:
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Frontend (in a second terminal):

```bash
cd frontend
npm install
npm start
```

For local development, configure an Angular dev-server proxy from `/api` to `http://localhost:8000`, or use the Compose setup above.
