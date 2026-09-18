from datetime import date, datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app import db

STATUSES = ("todo", "doing", "review", "done")
PRIORITIES = ("low", "medium", "high", "urgent")
PROJECT_STATES = ("active", "paused", "shipped")
THEMES = ("dark", "light")

task_labels = db.Table(
    "task_labels",
    db.Column("task_id", db.Integer, db.ForeignKey("task.id"), primary_key=True),
    db.Column("label_id", db.Integer, db.ForeignKey("label.id"), primary_key=True),
)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    theme = db.Column(db.String(20), default="dark", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    owned_projects = db.relationship("Project", backref="owner", lazy="dynamic", foreign_keys="Project.owner_id")
    comments = db.relationship("Comment", backref="author", lazy="dynamic")

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def initials(self) -> str:
        parts = [p for p in self.name.split() if p]
        if not parts:
            return "?"
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[-1][0]).upper()


class Membership(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), nullable=False)
    role = db.Column(db.String(20), default="member", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship("User", backref="memberships")
    __table_args__ = (db.UniqueConstraint("user_id", "project_id", name="uq_member_project"),)


class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, default="")
    color = db.Column(db.String(7), default="#f0b429")
    state = db.Column(db.String(20), default="active", nullable=False)
    due_date = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    tasks = db.relationship("Task", backref="project", lazy="dynamic", cascade="all, delete-orphan")
    members = db.relationship("Membership", backref="project", lazy="dynamic", cascade="all, delete-orphan")
    labels = db.relationship("Label", backref="project", lazy="dynamic", cascade="all, delete-orphan")
    activities = db.relationship("Activity", backref="project", lazy="dynamic", cascade="all, delete-orphan")

    def people(self):
        ids = {self.owner_id}
        for membership in self.members:
            ids.add(membership.user_id)
        return User.query.filter(User.id.in_(ids)).order_by(User.name).all()

    def progress(self) -> int:
        total = self.tasks.count()
        if not total:
            return 0
        done = self.tasks.filter_by(status="done").count()
        return round(100 * done / total)

    def overdue_count(self) -> int:
        today = date.today()
        return self.tasks.filter(Task.due_date.isnot(None), Task.due_date < today, Task.status != "done").count()


class Label(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), nullable=False)
    name = db.Column(db.String(40), nullable=False)
    color = db.Column(db.String(7), default="#7dd3c0", nullable=False)


class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), nullable=False)
    assignee_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    title = db.Column(db.String(180), nullable=False)
    details = db.Column(db.Text, default="")
    status = db.Column(db.String(20), default="todo", nullable=False, index=True)
    priority = db.Column(db.String(20), default="medium", nullable=False)
    due_date = db.Column(db.Date, nullable=True)
    position = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    assignee = db.relationship("User", foreign_keys=[assignee_id])
    comments = db.relationship("Comment", backref="task", lazy="dynamic", cascade="all, delete-orphan")
    checklist = db.relationship(
        "ChecklistItem", backref="task", lazy="dynamic", cascade="all, delete-orphan", order_by="ChecklistItem.position"
    )
    labels = db.relationship("Label", secondary=task_labels, backref="tasks")

    @property
    def overdue(self) -> bool:
        return bool(self.due_date and self.status != "done" and self.due_date < date.today())

    @property
    def checklist_progress(self) -> tuple[int, int]:
        items = self.checklist.all()
        if not items:
            return (0, 0)
        return (sum(1 for item in items if item.done), len(items))


class ChecklistItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey("task.id"), nullable=False)
    title = db.Column(db.String(180), nullable=False)
    done = db.Column(db.Boolean, default=False, nullable=False)
    position = db.Column(db.Integer, default=0, nullable=False)


class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey("task.id"), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Activity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), nullable=False)
    actor_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    message = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    actor = db.relationship("User")
