# Waypoint

Flask task manager with boards, inbox, agenda, labels, checklists, and notes. Runs locally and deploys on Render.

## Features

- Accounts with hashed passwords, profile, and dark/light theme
- Projects with state (active / paused / shipped)
- Kanban board plus compact list view
- Drag-and-drop status updates
- Quick-add tasks per column
- Priority, assignee, due dates, labels, checklists, and comments
- My work inbox and a two-week agenda
- Global search across projects and tasks
- Invite collaborators by the email they registered with
- Activity feed
- SQLite locally, Postgres in production via `DATABASE_URL`

## Run locally

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python run.py
```

Open http://127.0.0.1:5060

## Ship on Render

1. Push this repo to GitHub.
2. In Render, create a Blueprint from `render.yaml`, or a Python web service with:
   - Build: `pip install -r requirements.txt`
   - Start: `gunicorn wsgi:app --bind 0.0.0.0:$PORT`
3. Attach a Postgres database and set `DATABASE_URL` plus a strong `FLASK_SECRET_KEY`.

Invite teammates after they create their own Waypoint accounts — then add them from the project crew panel.
