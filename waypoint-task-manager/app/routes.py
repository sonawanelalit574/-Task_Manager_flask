from datetime import date, datetime, timedelta

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import case, or_

from app import db
from app.models import (
    PRIORITIES,
    PROJECT_STATES,
    STATUSES,
    Activity,
    ChecklistItem,
    Comment,
    Label,
    Membership,
    Project,
    Task,
    User,
)

bp = Blueprint("main", __name__)

STATUS_LABELS = {
    "todo": "To do",
    "doing": "In motion",
    "review": "Review",
    "done": "Shipped",
}

DEFAULT_LABELS = (
    ("Bug", "#ef6b6b"),
    ("Feature", "#7dd3c0"),
    ("Design", "#c4a5ff"),
    ("Ops", "#f0b429"),
)


def _priority_rank():
    return case(
        (Task.priority == "urgent", 0),
        (Task.priority == "high", 1),
        (Task.priority == "medium", 2),
        else_=3,
    )


def _accessible_projects():
    return (
        Project.query.outerjoin(Membership, Membership.project_id == Project.id)
        .filter(or_(Project.owner_id == current_user.id, Membership.user_id == current_user.id))
        .distinct()
        .order_by(Project.created_at.desc())
    )


def assigned_open_query():
    return (
        Task.query.join(Project)
        .outerjoin(Membership, Membership.project_id == Project.id)
        .filter(
            or_(Project.owner_id == current_user.id, Membership.user_id == current_user.id),
            Task.assignee_id == current_user.id,
            Task.status != "done",
        )
        .distinct()
        .order_by(Task.due_date.is_(None), Task.due_date, _priority_rank())
    )


def _get_project_or_404(project_id: int) -> Project:
    project = db.session.get(Project, project_id)
    if not project:
        abort(404)
    member_ids = {project.owner_id, *[m.user_id for m in project.members]}
    if current_user.id not in member_ids:
        abort(403)
    return project


def _get_task_or_404(task_id: int) -> tuple[Task, Project]:
    task = db.session.get(Task, task_id)
    if not task:
        abort(404)
    return task, _get_project_or_404(task.project_id)


def _parse_date(value: str | None):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _log(project: Project, message: str) -> None:
    db.session.add(Activity(project_id=project.id, actor_id=current_user.id, message=message))


def _ensure_default_labels(project: Project) -> None:
    if project.labels.count():
        return
    for name, color in DEFAULT_LABELS:
        db.session.add(Label(project_id=project.id, name=name, color=color))
    db.session.commit()


def _apply_task_labels(task: Task, project: Project) -> None:
    selected = {int(value) for value in request.form.getlist("label_ids") if value.isdigit()}
    allowed = {label.id: label for label in project.labels}
    task.labels = [allowed[label_id] for label_id in selected if label_id in allowed]


def _visible_tasks():
    return (
        Task.query.join(Project)
        .outerjoin(Membership, Membership.project_id == Project.id)
        .filter(or_(Project.owner_id == current_user.id, Membership.user_id == current_user.id))
        .distinct()
    )


@bp.route("/")
def landing():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    return render_template("landing.html")


@bp.route("/app")
@login_required
def dashboard():
    projects = _accessible_projects().all()
    q = (request.args.get("q") or "").strip().lower()
    state = request.args.get("state") or "all"
    if state in PROJECT_STATES:
        projects = [p for p in projects if p.state == state]
    if q:
        projects = [p for p in projects if q in p.name.lower() or q in (p.description or "").lower()]

    open_tasks = _visible_tasks().filter(Task.status != "done").count()
    due_soon = (
        _visible_tasks()
        .filter(Task.status != "done", Task.due_date.isnot(None), Task.due_date <= date.today() + timedelta(days=2))
        .count()
    )
    shipped = _visible_tasks().filter(Task.status == "done").count()
    recent = (
        Activity.query.join(Project)
        .outerjoin(Membership, Membership.project_id == Project.id)
        .filter(or_(Project.owner_id == current_user.id, Membership.user_id == current_user.id))
        .distinct()
        .order_by(Activity.created_at.desc())
        .limit(8)
        .all()
    )
    upcoming = (
        _visible_tasks()
        .filter(Task.status != "done", Task.due_date.isnot(None), Task.due_date >= date.today())
        .order_by(Task.due_date)
        .limit(6)
        .all()
    )
    return render_template(
        "dashboard.html",
        projects=projects,
        query=q,
        state=state,
        open_tasks=open_tasks,
        due_soon=due_soon,
        shipped=shipped,
        states=PROJECT_STATES,
        recent=recent,
        upcoming=upcoming,
    )


@bp.route("/app/inbox")
@login_required
def inbox():
    tasks = assigned_open_query().all()
    return render_template("inbox.html", tasks=tasks, status_labels=STATUS_LABELS)


@bp.route("/app/agenda")
@login_required
def agenda():
    start = date.today() - timedelta(days=3)
    end = date.today() + timedelta(days=14)
    tasks = (
        _visible_tasks()
        .filter(Task.due_date.isnot(None), Task.due_date >= start, Task.due_date <= end)
        .order_by(Task.due_date, _priority_rank())
        .all()
    )
    days = {}
    cursor = start
    while cursor <= end:
        days[cursor] = []
        cursor += timedelta(days=1)
    for task in tasks:
        days.setdefault(task.due_date, []).append(task)
    return render_template("agenda.html", days=days, today=date.today(), status_labels=STATUS_LABELS)


@bp.route("/app/search")
@login_required
def search():
    q = (request.args.get("q") or "").strip()
    tasks = []
    projects = []
    if q:
        like = f"%{q}%"
        tasks = _visible_tasks().filter(or_(Task.title.ilike(like), Task.details.ilike(like))).order_by(Task.updated_at.desc()).limit(40).all()
        projects = [p for p in _accessible_projects().all() if q.lower() in p.name.lower() or q.lower() in (p.description or "").lower()]
    return render_template("search.html", query=q, tasks=tasks, projects=projects, status_labels=STATUS_LABELS)


@bp.route("/projects/new", methods=["GET", "POST"])
@login_required
def project_new():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        if not name:
            flash("A project needs a name.")
            return redirect(url_for("main.project_new"))
        project = Project(
            owner_id=current_user.id,
            name=name,
            description=(request.form.get("description") or "").strip(),
            color=request.form.get("color") or "#f0b429",
            state=request.form.get("state") if request.form.get("state") in PROJECT_STATES else "active",
            due_date=_parse_date(request.form.get("due_date")),
        )
        db.session.add(project)
        db.session.flush()
        _log(project, f"created project {project.name}")
        db.session.commit()
        _ensure_default_labels(project)
        return redirect(url_for("main.project_board", project_id=project.id))
    return render_template("project_form.html", project=None, states=PROJECT_STATES)


@bp.route("/projects/<int:project_id>/edit", methods=["GET", "POST"])
@login_required
def project_edit(project_id: int):
    project = _get_project_or_404(project_id)
    if project.owner_id != current_user.id:
        abort(403)
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        if not name:
            flash("A project needs a name.")
            return redirect(url_for("main.project_edit", project_id=project.id))
        project.name = name
        project.description = (request.form.get("description") or "").strip()
        project.color = request.form.get("color") or project.color
        if request.form.get("state") in PROJECT_STATES:
            project.state = request.form.get("state")
        project.due_date = _parse_date(request.form.get("due_date"))
        _log(project, "updated project settings")
        db.session.commit()
        flash("Project updated.")
        return redirect(url_for("main.project_board", project_id=project.id))
    return render_template("project_form.html", project=project, states=PROJECT_STATES)


@bp.post("/projects/<int:project_id>/delete")
@login_required
def project_delete(project_id: int):
    project = _get_project_or_404(project_id)
    if project.owner_id != current_user.id:
        abort(403)
    db.session.delete(project)
    db.session.commit()
    flash("Project removed.")
    return redirect(url_for("main.dashboard"))


@bp.route("/projects/<int:project_id>")
@login_required
def project_board(project_id: int):
    project = _get_project_or_404(project_id)
    _ensure_default_labels(project)
    view = request.args.get("view") or "board"
    priority = request.args.get("priority") or "all"
    assignee = request.args.get("assignee") or "all"
    q = (request.args.get("q") or "").strip().lower()
    tasks = project.tasks.order_by(Task.position, Task.created_at).all()
    if priority in PRIORITIES:
        tasks = [t for t in tasks if t.priority == priority]
    if assignee == "me":
        tasks = [t for t in tasks if t.assignee_id == current_user.id]
    elif assignee.isdigit():
        tasks = [t for t in tasks if t.assignee_id == int(assignee)]
    if q:
        tasks = [t for t in tasks if q in t.title.lower() or q in (t.details or "").lower()]
    columns = {status: [] for status in STATUSES}
    for task in tasks:
        columns.setdefault(task.status, []).append(task)
    return render_template(
        "project.html",
        project=project,
        columns=columns,
        tasks=tasks,
        statuses=STATUSES,
        status_labels=STATUS_LABELS,
        priorities=PRIORITIES,
        people=project.people(),
        view=view,
        priority=priority,
        assignee=assignee,
        query=q,
        activities=project.activities.order_by(Activity.created_at.desc()).limit(12).all(),
    )


@bp.post("/projects/<int:project_id>/members")
@login_required
def add_member(project_id: int):
    project = _get_project_or_404(project_id)
    if project.owner_id != current_user.id:
        abort(403)
    email = (request.form.get("email") or "").strip().lower()
    user = User.query.filter_by(email=email).first()
    if not user:
        flash("No account uses that email yet.")
        return redirect(url_for("main.project_board", project_id=project.id))
    if user.id == project.owner_id or project.members.filter_by(user_id=user.id).first():
        flash("They already have access.")
        return redirect(url_for("main.project_board", project_id=project.id))
    db.session.add(Membership(user_id=user.id, project_id=project.id))
    _log(project, f"added {user.name} to the crew")
    db.session.commit()
    flash(f"{user.name} can now work this board.")
    return redirect(url_for("main.project_board", project_id=project.id))


@bp.post("/projects/<int:project_id>/members/<int:user_id>/remove")
@login_required
def remove_member(project_id: int, user_id: int):
    project = _get_project_or_404(project_id)
    if project.owner_id != current_user.id:
        abort(403)
    membership = project.members.filter_by(user_id=user_id).first_or_404()
    name = membership.user.name
    db.session.delete(membership)
    _log(project, f"removed {name} from the crew")
    db.session.commit()
    flash("Collaborator removed.")
    return redirect(url_for("main.project_board", project_id=project.id))


@bp.post("/projects/<int:project_id>/labels")
@login_required
def add_label(project_id: int):
    project = _get_project_or_404(project_id)
    name = (request.form.get("name") or "").strip()
    if not name:
        flash("Label needs a name.")
        return redirect(url_for("main.project_board", project_id=project.id))
    db.session.add(Label(project_id=project.id, name=name[:40], color=request.form.get("color") or "#7dd3c0"))
    db.session.commit()
    return redirect(url_for("main.project_board", project_id=project.id))


@bp.route("/projects/<int:project_id>/tasks/new", methods=["GET", "POST"])
@login_required
def task_new(project_id: int):
    project = _get_project_or_404(project_id)
    _ensure_default_labels(project)
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        if not title:
            flash("A task needs a title.")
            return redirect(url_for("main.task_new", project_id=project.id))
        status = request.form.get("status") if request.form.get("status") in STATUSES else "todo"
        assignee_id = request.form.get("assignee_id")
        allowed = {u.id for u in project.people()}
        task = Task(
            project_id=project.id,
            title=title,
            details=(request.form.get("details") or "").strip(),
            status=status,
            priority=request.form.get("priority") if request.form.get("priority") in PRIORITIES else "medium",
            due_date=_parse_date(request.form.get("due_date")),
            assignee_id=int(assignee_id) if assignee_id and int(assignee_id) in allowed else None,
            position=project.tasks.filter_by(status=status).count(),
        )
        db.session.add(task)
        db.session.flush()
        _apply_task_labels(task, project)
        _log(project, f"added task “{task.title}”")
        db.session.commit()
        return redirect(url_for("main.project_board", project_id=project.id))
    return render_template(
        "task_form.html",
        project=project,
        task=None,
        statuses=STATUSES,
        status_labels=STATUS_LABELS,
        priorities=PRIORITIES,
        people=project.people(),
    )


@bp.post("/projects/<int:project_id>/tasks/quick")
@login_required
def task_quick(project_id: int):
    project = _get_project_or_404(project_id)
    title = (request.form.get("title") or "").strip()
    status = request.form.get("status") if request.form.get("status") in STATUSES else "todo"
    if not title:
        flash("Type a task title first.")
        return redirect(url_for("main.project_board", project_id=project.id))
    task = Task(
        project_id=project.id,
        title=title,
        status=status,
        assignee_id=current_user.id,
        position=project.tasks.filter_by(status=status).count(),
    )
    db.session.add(task)
    _log(project, f"quick-added “{title}”")
    db.session.commit()
    return redirect(url_for("main.project_board", project_id=project.id, view=request.form.get("view") or "board"))


@bp.route("/tasks/<int:task_id>", methods=["GET", "POST"])
@login_required
def task_detail(task_id: int):
    task, project = _get_task_or_404(task_id)
    _ensure_default_labels(project)
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        if not title:
            flash("A task needs a title.")
            return redirect(url_for("main.task_detail", task_id=task.id))
        task.title = title
        task.details = (request.form.get("details") or "").strip()
        if request.form.get("status") in STATUSES:
            task.status = request.form.get("status")
        if request.form.get("priority") in PRIORITIES:
            task.priority = request.form.get("priority")
        task.due_date = _parse_date(request.form.get("due_date"))
        assignee_id = request.form.get("assignee_id")
        allowed = {u.id for u in project.people()}
        task.assignee_id = int(assignee_id) if assignee_id and int(assignee_id) in allowed else None
        _apply_task_labels(task, project)
        _log(project, f"updated “{task.title}”")
        db.session.commit()
        flash("Task saved.")
        return redirect(url_for("main.task_detail", task_id=task.id))
    return render_template(
        "task_form.html",
        project=project,
        task=task,
        statuses=STATUSES,
        status_labels=STATUS_LABELS,
        priorities=PRIORITIES,
        people=project.people(),
        comments=task.comments.order_by(Comment.created_at.desc()).all(),
        checklist=task.checklist.all(),
    )


@bp.post("/tasks/<int:task_id>/comments")
@login_required
def add_comment(task_id: int):
    task, project = _get_task_or_404(task_id)
    body = (request.form.get("body") or "").strip()
    if not body:
        flash("Write a note first.")
        return redirect(url_for("main.task_detail", task_id=task.id))
    db.session.add(Comment(task_id=task.id, author_id=current_user.id, body=body))
    _log(project, f"commented on “{task.title}”")
    db.session.commit()
    return redirect(url_for("main.task_detail", task_id=task.id))


@bp.post("/tasks/<int:task_id>/checklist")
@login_required
def add_checklist_item(task_id: int):
    task, _project = _get_task_or_404(task_id)
    title = (request.form.get("title") or "").strip()
    if not title:
        flash("Checklist items need a title.")
        return redirect(url_for("main.task_detail", task_id=task.id))
    db.session.add(
        ChecklistItem(task_id=task.id, title=title[:180], position=task.checklist.count(), done=False)
    )
    db.session.commit()
    return redirect(url_for("main.task_detail", task_id=task.id))


@bp.post("/checklist/<int:item_id>/toggle")
@login_required
def toggle_checklist_item(item_id: int):
    item = db.session.get(ChecklistItem, item_id)
    if not item:
        abort(404)
    _get_project_or_404(item.task.project_id)
    item.done = not item.done
    db.session.commit()
    if request.accept_mimetypes.best == "application/json" or request.is_json:
        return jsonify({"ok": True, "done": item.done})
    return redirect(url_for("main.task_detail", task_id=item.task_id))


@bp.post("/checklist/<int:item_id>/delete")
@login_required
def delete_checklist_item(item_id: int):
    item = db.session.get(ChecklistItem, item_id)
    if not item:
        abort(404)
    task_id = item.task_id
    _get_project_or_404(item.task.project_id)
    db.session.delete(item)
    db.session.commit()
    return redirect(url_for("main.task_detail", task_id=task_id))


@bp.post("/tasks/<int:task_id>/delete")
@login_required
def task_delete(task_id: int):
    task, project = _get_task_or_404(task_id)
    title = task.title
    db.session.delete(task)
    _log(project, f"deleted “{title}”")
    db.session.commit()
    flash("Task deleted.")
    return redirect(url_for("main.project_board", project_id=project.id))


@bp.post("/tasks/<int:task_id>/move")
@login_required
def task_move(task_id: int):
    task, project = _get_task_or_404(task_id)
    payload = request.get_json(silent=True) or {}
    status = payload.get("status")
    if status not in STATUSES:
        return jsonify({"ok": False, "error": "Invalid status"}), 400
    task.status = status
    task.position = int(payload.get("position") or 0)
    _log(project, f"moved “{task.title}” to {STATUS_LABELS[status]}")
    db.session.commit()
    return jsonify({"ok": True})
