from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="customer")  # admin or customer
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # A customer can own multiple houses
    houses = db.relationship("House", back_populates="owner", lazy="dynamic")

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    def __repr__(self) -> str:
        return f"<User {self.email} ({self.role})>"


class House(db.Model):
    __tablename__ = "houses"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)  # e.g. "Main Residence"
    address = db.Column(db.String(255), nullable=False)
    notes = db.Column(db.Text)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    owner = db.relationship("User", back_populates="houses")
    checklist_items = db.relationship(
        "ChecklistItem", back_populates="house", lazy="dynamic", cascade="all, delete-orphan"
    )
    messages = db.relationship(
        "Message", back_populates="house", lazy="dynamic", cascade="all, delete-orphan"
    )
    photos = db.relationship(
        "Photo", back_populates="house", lazy="dynamic", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<House {self.name} - {self.address}>"


class ChecklistItem(db.Model):
    __tablename__ = "checklist_items"

    id = db.Column(db.Integer, primary_key=True)
    house_id = db.Column(db.Integer, db.ForeignKey("houses.id"), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    category = db.Column(db.String(50), default="General")  # HVAC, Plumbing, Electrical, Seasonal, etc.
    status = db.Column(db.String(20), default="pending")  # pending, in_progress, completed, overdue
    due_date = db.Column(db.Date)
    priority = db.Column(db.String(20), default="medium")  # low, medium, high
    notes = db.Column(db.Text)  # item-specific notes / messages
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = db.Column(db.DateTime)

    house = db.relationship("House", back_populates="checklist_items")
    photos = db.relationship(
        "Photo", back_populates="checklist_item", lazy="dynamic", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<ChecklistItem {self.title} ({self.status})>"


class Photo(db.Model):
    __tablename__ = "photos"

    id = db.Column(db.Integer, primary_key=True)
    house_id = db.Column(db.Integer, db.ForeignKey("houses.id"), nullable=False)
    checklist_item_id = db.Column(db.Integer, db.ForeignKey("checklist_items.id"), nullable=True)
    filename = db.Column(db.String(255), nullable=False)
    caption = db.Column(db.String(255))
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    house = db.relationship("House", back_populates="photos")
    checklist_item = db.relationship("ChecklistItem", back_populates="photos")
    uploaded_by = db.relationship("User")

    def __repr__(self) -> str:
        return f"<Photo {self.filename}>"


class Message(db.Model):
    """General message board per house (in addition to item-level notes)."""
    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True)
    house_id = db.Column(db.Integer, db.ForeignKey("houses.id"), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    house = db.relationship("House", back_populates="messages")
    author = db.relationship("User")

    def __repr__(self) -> str:
        return f"<Message {self.id} by {self.author_id}>"
