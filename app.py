from flask import Flask, render_template, request, session, redirect, url_for, abort
from datetime import date
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

ROLE_ADMIN = "Administrator"
ROLE_USER = "User"

ASSET_STATUS_ACTIVE = "Active"
ASSET_STATUS_MISSING = "Missing"
ASSET_STATUS_LENT = "Lent"
ASSET_STATUS_DISPOSED = "Disposed"

MANUAL_STATUS_TRANSITIONS = {
    ASSET_STATUS_ACTIVE: {ASSET_STATUS_MISSING, ASSET_STATUS_DISPOSED},
    ASSET_STATUS_MISSING: {ASSET_STATUS_ACTIVE, ASSET_STATUS_DISPOSED},
    ASSET_STATUS_LENT: set(),
    ASSET_STATUS_DISPOSED: set(),
}

app = Flask(__name__)
app.config["SECRET_KEY"] = "dev-secret-key"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///him.db"

db = SQLAlchemy(app)
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)


def get_current_user():
    user_id = session.get("user_id")
    if user_id is None:
        return None
    return db.session.get(User, user_id)


@app.route("/")
def home():
    return "Home Inventory Manager"

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        user = db.session.execute(
            db.select(User).where(User.username == username)
        ).scalar_one_or_none()

        if user and check_password_hash(user.password_hash, password):
            session["user_id"] = user.id
            return redirect(url_for("dashboard"))
        else:
            return render_template("login.html")


    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("user_id", None)
    return redirect(url_for("login"))


@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return "Welcome to the dashboard"

@app.route("/admin")
def admin():
    user = get_current_user()
    if user is None:
        return redirect(url_for("login"))
    # Restrict this route to Administrator accounts
    if user.role != ROLE_ADMIN:
        abort(403)
    return "Administrator access granted"

@app.route("/categories")
def categories():
    user = get_current_user()
    if user is None:
        return redirect(url_for("login"))
    
    category_list = db.session.execute(
    db.select(Category).order_by(Category.name)
    ).scalars().all()
    return render_template("categories.html", categories=category_list,user=user)

@app.route("/categories/add", methods=["POST"])
def add_category():
    user = get_current_user()
    if user is None:
        return redirect(url_for("login"))
    if user.role != ROLE_ADMIN:
        abort(403)
    name = request.form["name"].strip()
    if name:
        existing_category = db.session.execute(
            db.select(Category).where(Category.name == name)
        ).scalar_one_or_none()

        if existing_category is None:
            category = Category(name=name)
            db.session.add(category)
            db.session.commit()
    return redirect(url_for("categories"))

@app.route("/categories/<int:category_id>/update", methods=["POST"])
def update_category(category_id):
    user = get_current_user()

    if user is None:
        return redirect(url_for("login"))

    if user.role != ROLE_ADMIN:
        abort(403)

    category = db.session.get(Category, category_id)

    if category is None:
        abort(404)

    name = request.form["name"].strip()

    if name:
        existing_category = db.session.execute(
            db.select(Category).where(
                Category.name == name,
                Category.id != category_id
            )
        ).scalar_one_or_none()

        if existing_category is None:
            category.name = name
            db.session.commit()

    return redirect(url_for("categories"))

@app.route("/categories/<int:category_id>/delete", methods=["POST"])
def delete_category(category_id):
    user = get_current_user()

    if user is None:
        return redirect(url_for("login"))

    if user.role != ROLE_ADMIN:
        abort(403)

    category = db.session.get(Category, category_id)

    if category is None:
        abort(404)

    db.session.delete(category)
    db.session.commit()

    return redirect(url_for("categories"))

class Location(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
class Asset(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(255))
    status = db.Column(db.String(20), nullable=False, default=ASSET_STATUS_ACTIVE)

    category_id = db.Column(
        db.Integer,
        db.ForeignKey("category.id"),
        nullable=False
    )
    category = db.relationship("Category")

    location_id = db.Column(
        db.Integer,
        db.ForeignKey("location.id"),
        nullable=False
    )
    location = db.relationship("Location")
    loans = db.relationship("Loan", back_populates="asset", cascade="all, delete-orphan")
    go_bag_item = db.relationship("GoBagItem", back_populates="asset", uselist=False, cascade="all, delete-orphan")


class Loan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey("asset.id"), nullable=False)
    borrower_name = db.Column(db.String(100), nullable=False)
    lent_date = db.Column(db.Date, nullable=False, default=date.today)
    due_date = db.Column(db.Date)
    returned_date = db.Column(db.Date)

    asset = db.relationship("Asset", back_populates="loans")


class GoBagItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey("asset.id"), unique=True, nullable=False)
    priority = db.Column(db.String(20), nullable=False, default="Medium")
    notes = db.Column(db.String(255))

    asset = db.relationship("Asset", back_populates="go_bag_item")


# Create all tables only after every model has been declared.
with app.app_context():
    db.create_all()


@app.route("/locations")
def locations():
    user = get_current_user()

    if user is None:
        return redirect(url_for("login"))

    location_list = db.session.execute(
        db.select(Location).order_by(Location.name)
    ).scalars().all()

    return render_template(
        "locations.html",
        locations=location_list,
        user=user
    )


@app.route("/assets")
def assets():
    user = get_current_user()

    if user is None:
        return redirect(url_for("login"))

    asset_list = db.session.execute(
        db.select(Asset).order_by(Asset.name)
    ).scalars().all()

    categories = db.session.execute(
        db.select(Category).order_by(Category.name)
    ).scalars().all()

    locations = db.session.execute(
        db.select(Location).order_by(Location.name)
    ).scalars().all()

    active_loan_list = db.session.execute(
        db.select(Loan).where(Loan.returned_date.is_(None))
    ).scalars().all()
    active_loans = {loan.asset_id: loan for loan in active_loan_list}

    return render_template(
        "assets.html",
        assets=asset_list,
        categories=categories,
        locations=locations,
        active_loans=active_loans,
        user=user
    )

   

@app.route("/locations/add", methods=["POST"])
def add_location():
    user = get_current_user()

    if user is None:
        return redirect(url_for("login"))

    if user.role != ROLE_ADMIN:
        abort(403)

    name = request.form["name"].strip()

    if name:
        existing_location = db.session.execute(
            db.select(Location).where(Location.name == name)
        ).scalar_one_or_none()

        if existing_location is None:
            location = Location(name=name)
            db.session.add(location)
            db.session.commit()

    return redirect(url_for("locations"))


@app.route("/assets/add", methods=["POST"])
def add_asset():
    user = get_current_user()

    if user is None:
        return redirect(url_for("login"))

    name = request.form["name"].strip()
    description = request.form["description"].strip()
    category_id = request.form["category_id"]
    location_id = request.form["location_id"]

    category = db.session.get(Category, int(category_id))
    location = db.session.get(Location, int(location_id))

    if name and category is not None and location is not None:
        asset = Asset(
            name=name,
            description=description,
            status=ASSET_STATUS_ACTIVE,
            category_id=int(category_id),
            location_id=int(location_id)
        )

        db.session.add(asset)
        db.session.commit()

    return redirect(url_for("assets"))


@app.route("/locations/<int:location_id>/update", methods=["POST"])
def update_location(location_id):
    user = get_current_user()

    if user is None:
        return redirect(url_for("login"))

    if user.role != ROLE_ADMIN:
        abort(403)

    location = db.session.get(Location, location_id)

    if location is None:
        abort(404)

    name = request.form["name"].strip()

    if name:
        existing_location = db.session.execute(
            db.select(Location).where(
                Location.name == name,
                Location.id != location_id
            )
        ).scalar_one_or_none()

        if existing_location is None:
            location.name = name
            db.session.commit()

    return redirect(url_for("locations"))


@app.route("/locations/<int:location_id>/delete", methods=["POST"])
def delete_location(location_id):
    user = get_current_user()

    if user is None:
        return redirect(url_for("login"))

    if user.role != ROLE_ADMIN:
        abort(403)

    location = db.session.get(Location, location_id)

    if location is None:
        abort(404)

    db.session.delete(location)
    db.session.commit()

    return redirect(url_for("locations"))


@app.route("/assets/<int:asset_id>/update", methods=["POST"])
def update_asset(asset_id):
    user = get_current_user()

    if user is None:
        return redirect(url_for("login"))

    asset = db.session.get(Asset, asset_id)

    if asset is None:
        abort(404)

    name = request.form["name"].strip()
    description = request.form["description"].strip()
    category_id = request.form["category_id"]
    location_id = request.form["location_id"]

    category = db.session.get(Category, int(category_id))
    location = db.session.get(Location, int(location_id))

    if name and category is not None and location is not None:
        asset.name = name
        asset.description = description
        asset.category_id = category.id
        asset.location_id = location.id

        db.session.commit()

    return redirect(url_for("assets"))


@app.route("/assets/<int:asset_id>/delete", methods=["POST"])
def delete_asset(asset_id):
    user = get_current_user()

    if user is None:
        return redirect(url_for("login"))

    asset = db.session.get(Asset, asset_id)

    if asset is None:
        abort(404)

    db.session.delete(asset)
    db.session.commit()

    return redirect(url_for("assets"))


@app.route("/assets/<int:asset_id>/move", methods=["POST"])
def move_asset(asset_id):
    user = get_current_user()

    if user is None:
        return redirect(url_for("login"))

    asset = db.session.get(Asset, asset_id)

    if asset is None:
        abort(404)

    location_id = request.form["location_id"]
    location = db.session.get(Location, int(location_id))

    if location is not None:
        asset.location_id = location.id
        db.session.commit()

    return redirect(url_for("assets"))

@app.route("/assets/<int:asset_id>/status", methods=["POST"])
def update_asset_status(asset_id):
    user = get_current_user()

    if user is None:
        return redirect(url_for("login"))

    asset = db.session.get(Asset, asset_id)

    if asset is None:
        abort(404)

    new_status = request.form.get("status", "").strip()
    allowed_transitions = MANUAL_STATUS_TRANSITIONS.get(asset.status, set())

    if new_status not in allowed_transitions:
        abort(400)

    asset.status = new_status
    db.session.commit()

    return redirect(url_for("assets"))


@app.route("/go-bag")
def go_bag():
    user = get_current_user()

    if user is None:
        return redirect(url_for("login"))

    items = db.session.execute(
        db.select(GoBagItem).join(GoBagItem.asset).order_by(GoBagItem.priority, Asset.name)
    ).scalars().all()

    return render_template("go_bag.html", items=items, user=user)


@app.route("/assets/<int:asset_id>/go-bag/add", methods=["POST"])
def add_to_go_bag(asset_id):
    user = get_current_user()

    if user is None:
        return redirect(url_for("login"))

    asset = db.session.get(Asset, asset_id)
    if asset is None:
        abort(404)

    existing_item = db.session.execute(
        db.select(GoBagItem).where(GoBagItem.asset_id == asset_id)
    ).scalar_one_or_none()

    if existing_item is not None:
        abort(400)

    priority = request.form.get("priority", "Medium").strip()
    notes = request.form.get("notes", "").strip()

    if priority not in {"High", "Medium", "Low"}:
        abort(400)

    item = GoBagItem(
        asset_id=asset.id,
        priority=priority,
        notes=notes or None
    )
    db.session.add(item)
    db.session.commit()

    return redirect(url_for("assets"))


@app.route("/go-bag/<int:item_id>/remove", methods=["POST"])
def remove_from_go_bag(item_id):
    user = get_current_user()

    if user is None:
        return redirect(url_for("login"))

    item = db.session.get(GoBagItem, item_id)
    if item is None:
        abort(404)

    db.session.delete(item)
    db.session.commit()

    return redirect(url_for("go_bag"))


@app.route("/assets/<int:asset_id>/lend", methods=["POST"])
def lend_asset(asset_id):
    user = get_current_user()

    if user is None:
        return redirect(url_for("login"))

    asset = db.session.get(Asset, asset_id)

    if asset is None:
        abort(404)

    if asset.status != ASSET_STATUS_ACTIVE:
        abort(400)

    existing_loan = db.session.execute(
        db.select(Loan).where(
            Loan.asset_id == asset_id,
            Loan.returned_date.is_(None)
        )
    ).scalar_one_or_none()

    if existing_loan is not None:
        abort(400)

    borrower_name = request.form.get("borrower_name", "").strip()
    due_date_text = request.form.get("due_date", "").strip()

    if not borrower_name:
        abort(400)

    due_date = None
    if due_date_text:
        try:
            due_date = date.fromisoformat(due_date_text)
        except ValueError:
            abort(400)

        if due_date < date.today():
            abort(400)

    loan = Loan(
        asset_id=asset.id,
        borrower_name=borrower_name,
        lent_date=date.today(),
        due_date=due_date
    )

    asset.status = ASSET_STATUS_LENT
    db.session.add(loan)
    db.session.commit()

    return redirect(url_for("assets"))


@app.route("/loans/<int:loan_id>/return", methods=["POST"])
def return_asset(loan_id):
    user = get_current_user()

    if user is None:
        return redirect(url_for("login"))

    loan = db.session.get(Loan, loan_id)

    if loan is None:
        abort(404)

    if loan.returned_date is not None:
        abort(400)

    if loan.asset.status != ASSET_STATUS_LENT:
        abort(400)

    loan.returned_date = date.today()
    loan.asset.status = ASSET_STATUS_ACTIVE
    db.session.commit()

    return redirect(url_for("assets"))


@app.route("/loans")
def loan_history():
    user = get_current_user()

    if user is None:
        return redirect(url_for("login"))

    loans = db.session.execute(
        db.select(Loan).order_by(Loan.lent_date.desc(), Loan.id.desc())
    ).scalars().all()

    return render_template("loans.html", loans=loans, user=user)
