import os
from datetime import datetime, date
from functools import wraps

from flask import (
    Flask,
    render_template,
    redirect,
    url_for,
    flash,
    request,
    abort,
    current_app,
)
from flask_login import (
    LoginManager,
    login_user,
    logout_user,
    login_required,
    current_user,
)
from werkzeug.utils import secure_filename
from PIL import Image

from models import db, User, House, ChecklistItem, Photo, Message

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me-in-production")

# Database: use DATABASE_URL from Render (Postgres) when present, otherwise local SQLite
database_url = os.environ.get("DATABASE_URL")
if database_url:
    # Render gives "postgres://..." — SQLAlchemy needs "postgresql://"
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
else:
    # Local development fallback
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:////tmp/home_maintenance.db"
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"connect_args": {"timeout": 30}}

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = os.path.join(os.path.dirname(__file__), "static", "uploads")
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8 MB
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message_category = "warning"


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_photo(file_storage, house_id: int, checklist_item_id=None) -> Photo | None:
    if not file_storage or not allowed_file(file_storage.filename):
        return None
    filename = secure_filename(file_storage.filename)
    # Make unique
    base, ext = os.path.splitext(filename)
    unique_name = f"{base}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}{ext}"
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], unique_name)

    # Resize large images for web
    try:
        img = Image.open(file_storage.stream)
        img.thumbnail((1600, 1600))
        img.save(path, optimize=True, quality=85)
    except Exception:
        file_storage.save(path)

    photo = Photo(
        house_id=house_id,
        checklist_item_id=checklist_item_id,
        filename=unique_name,
        caption=request.form.get("caption", "").strip() or None,
        uploaded_by_id=current_user.id,
    )
    db.session.add(photo)
    return photo


def user_can_access_house(house: House) -> bool:
    if current_user.is_admin:
        return True
    return house.owner_id == current_user.id


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user, remember=True)
            flash(f"Welcome back, {user.name}!", "success")
            next_page = request.args.get("next")
            return redirect(next_page or url_for("dashboard"))
        flash("Invalid email or password.", "danger")
    return render_template("auth/login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@app.route("/")
@login_required
def dashboard():
    if current_user.is_admin:
        houses = House.query.order_by(House.created_at.desc()).all()
        customers = User.query.filter_by(role="customer").order_by(User.name).all()
        return render_template(
            "admin/dashboard.html",
            houses=houses,
            customers=customers,
        )
    else:
        houses = current_user.houses.order_by(House.name).all()
        return render_template("dashboard.html", houses=houses)


# ---------------------------------------------------------------------------
# House views (shared)
# ---------------------------------------------------------------------------
@app.route("/house/<int:house_id>")
@login_required
def house_detail(house_id):
    house = db.session.get(House, house_id) or abort(404)
    if not user_can_access_house(house):
        abort(403)

    items = house.checklist_items.order_by(
        ChecklistItem.status, ChecklistItem.due_date, ChecklistItem.priority.desc()
    ).all()
    messages = house.messages.order_by(Message.created_at.desc()).limit(50).all()
    gallery_photos = house.photos.filter_by(checklist_item_id=None).order_by(Photo.created_at.desc()).all()

    # Group items by category for nicer display
    categories = {}
    for item in items:
        categories.setdefault(item.category or "General", []).append(item)

    return render_template(
        "house_detail.html",
        house=house,
        categories=categories,
        messages=messages,
        gallery_photos=gallery_photos,
    )


@app.route("/house/<int:house_id>/item/<int:item_id>/status", methods=["POST"])
@login_required
def update_item_status(house_id, item_id):
    house = db.session.get(House, house_id) or abort(404)
    if not user_can_access_house(house):
        abort(403)
    item = db.session.get(ChecklistItem, item_id) or abort(404)
    if item.house_id != house.id:
        abort(404)

    new_status = request.form.get("status")
    if new_status in ("pending", "in_progress", "completed", "overdue"):
        item.status = new_status
        if new_status == "completed":
            item.completed_at = datetime.utcnow()
        else:
            item.completed_at = None
        db.session.commit()
        flash("Status updated.", "success")
    return redirect(url_for("house_detail", house_id=house.id))


@app.route("/house/<int:house_id>/message", methods=["POST"])
@login_required
def post_message(house_id):
    house = db.session.get(House, house_id) or abort(404)
    if not user_can_access_house(house):
        abort(403)

    body = request.form.get("body", "").strip()
    if not body:
        flash("Message cannot be empty.", "warning")
        return redirect(url_for("house_detail", house_id=house.id))

    msg = Message(house_id=house.id, author_id=current_user.id, body=body)
    db.session.add(msg)
    db.session.commit()
    flash("Message posted.", "success")
    return redirect(url_for("house_detail", house_id=house.id))


# ---------------------------------------------------------------------------
# Admin: Customers
# ---------------------------------------------------------------------------
@app.route("/admin/customers", methods=["GET", "POST"])
@login_required
@admin_required
def admin_customers():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "changeme123")

        if not name or not email:
            flash("Name and email are required.", "danger")
        elif User.query.filter_by(email=email).first():
            flash("A user with that email already exists.", "danger")
        else:
            user = User(name=name, email=email, role="customer")
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash(f"Customer {name} created. Temporary password: {password}", "success")
            return redirect(url_for("admin_customers"))

    customers = User.query.filter_by(role="customer").order_by(User.name).all()
    return render_template("admin/customers.html", customers=customers)


# ---------------------------------------------------------------------------
# Admin: Houses
# ---------------------------------------------------------------------------
@app.route("/admin/houses", methods=["GET", "POST"])
@login_required
@admin_required
def admin_houses():
    customers = User.query.filter_by(role="customer").order_by(User.name).all()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        address = request.form.get("address", "").strip()
        owner_id = request.form.get("owner_id", type=int)
        notes = request.form.get("notes", "").strip()

        if not name or not address or not owner_id:
            flash("Name, address, and customer are required.", "danger")
        else:
            house = House(name=name, address=address, owner_id=owner_id, notes=notes or None)
            db.session.add(house)
            db.session.commit()
            flash(f"House '{name}' created.", "success")
            return redirect(url_for("admin_houses"))

    houses = House.query.order_by(House.created_at.desc()).all()
    return render_template("admin/houses.html", houses=houses, customers=customers)


# ---------------------------------------------------------------------------
# Admin: Checklist items
# ---------------------------------------------------------------------------
@app.route("/admin/house/<int:house_id>/items", methods=["GET", "POST"])
@login_required
@admin_required
def admin_items(house_id):
    house = db.session.get(House, house_id) or abort(404)

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        category = request.form.get("category", "General").strip() or "General"
        priority = request.form.get("priority", "medium")
        due_date_str = request.form.get("due_date", "").strip()
        notes = request.form.get("notes", "").strip()

        if not title:
            flash("Title is required.", "danger")
        else:
            due_date = None
            if due_date_str:
                try:
                    due_date = datetime.strptime(due_date_str, "%Y-%m-%d").date()
                except ValueError:
                    flash("Invalid due date format.", "warning")

            item = ChecklistItem(
                house_id=house.id,
                title=title,
                description=description or None,
                category=category,
                priority=priority,
                due_date=due_date,
                notes=notes or None,
            )
            db.session.add(item)
            db.session.commit()
            flash("Checklist item added.", "success")
            return redirect(url_for("admin_items", house_id=house.id))

    items = house.checklist_items.order_by(ChecklistItem.category, ChecklistItem.title).all()
    return render_template("admin/items.html", house=house, items=items)


@app.route("/admin/item/<int:item_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def admin_edit_item(item_id):
    item = db.session.get(ChecklistItem, item_id) or abort(404)
    house = item.house

    if request.method == "POST":
        item.title = request.form.get("title", "").strip() or item.title
        item.description = request.form.get("description", "").strip() or None
        item.category = request.form.get("category", "General").strip() or "General"
        item.priority = request.form.get("priority", "medium")
        item.status = request.form.get("status", item.status)
        item.notes = request.form.get("notes", "").strip() or None

        due_date_str = request.form.get("due_date", "").strip()
        if due_date_str:
            try:
                item.due_date = datetime.strptime(due_date_str, "%Y-%m-%d").date()
            except ValueError:
                pass
        else:
            item.due_date = None

        if item.status == "completed" and not item.completed_at:
            item.completed_at = datetime.utcnow()
        elif item.status != "completed":
            item.completed_at = None

        db.session.commit()
        flash("Item updated.", "success")
        return redirect(url_for("admin_items", house_id=house.id))

    return render_template("admin/edit_item.html", item=item, house=house)


@app.route("/admin/item/<int:item_id>/delete", methods=["POST"])
@login_required
@admin_required
def admin_delete_item(item_id):
    item = db.session.get(ChecklistItem, item_id) or abort(404)
    house_id = item.house_id
    db.session.delete(item)
    db.session.commit()
    flash("Item deleted.", "info")
    return redirect(url_for("admin_items", house_id=house_id))


# ---------------------------------------------------------------------------
# Photo uploads
# ---------------------------------------------------------------------------
@app.route("/house/<int:house_id>/upload", methods=["POST"])
@login_required
def upload_photo(house_id):
    house = db.session.get(House, house_id) or abort(404)
    if not user_can_access_house(house):
        abort(403)

    # Only admins can upload for now (customers can view)
    if not current_user.is_admin:
        flash("Only technicians can upload photos.", "warning")
        return redirect(url_for("house_detail", house_id=house.id))

    file = request.files.get("photo")
    item_id = request.form.get("checklist_item_id", type=int) or None

    if item_id:
        item = db.session.get(ChecklistItem, item_id)
        if not item or item.house_id != house.id:
            item_id = None

    photo = save_photo(file, house.id, item_id)
    if photo:
        db.session.commit()
        flash("Photo uploaded.", "success")
    else:
        flash("Invalid or missing image file.", "danger")
    return redirect(url_for("house_detail", house_id=house.id))


# ---------------------------------------------------------------------------
# Seed data (run once)
# ---------------------------------------------------------------------------
def seed_data():
    if User.query.first():
        return  # already seeded

    admin = User(name="Tech Admin", email="admin@example.com", role="admin")
    admin.set_password("admin123")
    db.session.add(admin)

    customer1 = User(name="Sarah Johnson", email="sarah@example.com", role="customer")
    customer1.set_password("customer123")
    db.session.add(customer1)

    customer2 = User(name="Mike Chen", email="mike@example.com", role="customer")
    customer2.set_password("customer123")
    db.session.add(customer2)
    db.session.flush()

    house1 = House(
        name="Main Residence",
        address="123 Oak Street, Springfield, IL 62701",
        notes="2-story colonial, built 1998. HVAC system replaced 2021.",
        owner_id=customer1.id,
    )
    house2 = House(
        name="Lake Cabin",
        address="45 Pine Road, Lakeview, IL 60000",
        notes="Seasonal property. Winterize each October.",
        owner_id=customer1.id,
    )
    house3 = House(
        name="Downtown Condo",
        address="800 Main Ave #12B, Chicago, IL 60601",
        notes="High-rise unit. Building handles exterior maintenance.",
        owner_id=customer2.id,
    )
    db.session.add_all([house1, house2, house3])
    db.session.flush()

    sample_items = [
        # House 1
        ChecklistItem(
            house_id=house1.id,
            title="Replace HVAC filters",
            description="Use MERV-11 filters. Check both upstairs and downstairs units.",
            category="HVAC",
            status="pending",
            priority="high",
            due_date=date(2026, 10, 15),
        ),
        ChecklistItem(
            house_id=house1.id,
            title="Inspect roof and gutters",
            description="Look for missing shingles, clean debris from gutters.",
            category="Exterior",
            status="pending",
            priority="medium",
            due_date=date(2026, 11, 1),
        ),
        ChecklistItem(
            house_id=house1.id,
            title="Test smoke & CO detectors",
            description="Press test button on every unit. Replace batteries yearly.",
            category="Safety",
            status="completed",
            priority="high",
            due_date=date(2026, 9, 1),
            completed_at=datetime(2026, 8, 28),
        ),
        ChecklistItem(
            house_id=house1.id,
            title="Winterize outdoor faucets",
            description="Shut off interior valves and open outdoor spigots.",
            category="Plumbing",
            status="pending",
            priority="medium",
            due_date=date(2026, 10, 20),
        ),
        # House 2
        ChecklistItem(
            house_id=house2.id,
            title="Drain and shut off water",
            description="Full winterization procedure for seasonal property.",
            category="Plumbing",
            status="pending",
            priority="high",
            due_date=date(2026, 10, 10),
        ),
        ChecklistItem(
            house_id=house2.id,
            title="Clean chimney",
            description="Schedule professional sweep before first fire.",
            category="Safety",
            status="pending",
            priority="medium",
            due_date=date(2026, 10, 25),
        ),
        # House 3
        ChecklistItem(
            house_id=house3.id,
            title="Replace refrigerator water filter",
            description="Model number on filter housing.",
            category="Appliances",
            status="pending",
            priority="low",
            due_date=date(2026, 11, 15),
        ),
    ]
    db.session.add_all(sample_items)

    msg1 = Message(
        house_id=house1.id,
        author_id=admin.id,
        body="Welcome! I've set up your initial seasonal checklist. Please review and let me know if anything is missing.",
    )
    msg2 = Message(
        house_id=house1.id,
        author_id=customer1.id,
        body="Thanks! The HVAC filters are the most urgent for us right now.",
    )
    db.session.add_all([msg1, msg2])
    db.session.commit()
    print("Seed data created successfully.")


# ---------------------------------------------------------------------------
# CLI / startup
# ---------------------------------------------------------------------------
@app.cli.command("init-db")
def init_db():
    """Initialize the database and seed sample data."""
    db.create_all()
    seed_data()
    print("Database initialized.")


with app.app_context():
    db.create_all()
    seed_data()


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
