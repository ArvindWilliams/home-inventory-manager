from flask import Flask, render_template, request, session, redirect, url_for, abort, Response
from datetime import date
import csv
import io
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
    user = get_current_user()
    if user is not None:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

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
            return render_template("login.html", login_error=True)


    return render_template("login.html", login_error=False)

@app.route("/logout")
def logout():
    session.pop("user_id", None)
    return redirect(url_for("login"))


@app.route("/dashboard")
def dashboard():
    user = get_current_user()
    if user is None:
        return redirect(url_for("login"))

    return render_template("dashboard.html", user=user)

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

    category_asset_counts = {category.id: 0 for category in category_list}
    assigned_category_ids = db.session.execute(
        db.select(Asset.category_id)
    ).scalars().all()

    for category_id in assigned_category_ids:
        category_asset_counts[category_id] = category_asset_counts.get(category_id, 0) + 1

    return render_template(
        "categories.html",
        categories=category_list,
        category_asset_counts=category_asset_counts,
        error=request.args.get("error", ""),
        user=user
    )

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

    assigned_assets = db.session.execute(
        db.select(Asset.id).where(Asset.category_id == category.id)
    ).scalars().all()

    if assigned_assets:
        count = len(assigned_assets)
        noun = "asset" if count == 1 else "assets"
        return redirect(url_for(
            "categories",
            error=f"Cannot delete {category.name}: {count} {noun} still use this category. Reassign them first."
        ))

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
    insurance_record = db.relationship("InsuranceRecord", back_populates="asset", uselist=False, cascade="all, delete-orphan")


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


class InsuranceRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey("asset.id"), unique=True, nullable=False)
    provider = db.Column(db.String(100))
    policy_number = db.Column(db.String(100))
    insured_value = db.Column(db.Float)
    evidence_reference = db.Column(db.String(255))
    claim_ready = db.Column(db.Boolean, nullable=False, default=False)

    asset = db.relationship("Asset", back_populates="insurance_record")


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

    location_asset_counts = {location.id: 0 for location in location_list}
    assigned_location_ids = db.session.execute(
        db.select(Asset.location_id)
    ).scalars().all()

    for location_id in assigned_location_ids:
        location_asset_counts[location_id] = location_asset_counts.get(location_id, 0) + 1

    return render_template(
        "locations.html",
        locations=location_list,
        location_asset_counts=location_asset_counts,
        error=request.args.get("error", ""),
        user=user
    )


@app.route("/assets")
def assets():
    user = get_current_user()

    if user is None:
        return redirect(url_for("login"))

    search = request.args.get("search", "").strip()
    category_id = request.args.get("category_id", "").strip()
    location_id = request.args.get("location_id", "").strip()
    status = request.args.get("status", "").strip()

    query = db.select(Asset)

    if search:
        query = query.where(Asset.name.ilike(f"%{search}%"))

    if category_id:
        query = query.where(Asset.category_id == int(category_id))

    if location_id:
        query = query.where(Asset.location_id == int(location_id))

    if status:
        query = query.where(Asset.status == status)

    asset_list = db.session.execute(
        query.order_by(Asset.name)
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
        search=search,
        selected_category_id=category_id,
        selected_location_id=location_id,
        selected_status=status,
        asset_statuses=[
            ASSET_STATUS_ACTIVE,
            ASSET_STATUS_MISSING,
            ASSET_STATUS_LENT,
            ASSET_STATUS_DISPOSED,
        ],
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

    assigned_assets = db.session.execute(
        db.select(Asset.id).where(Asset.location_id == location.id)
    ).scalars().all()

    if assigned_assets:
        count = len(assigned_assets)
        noun = "asset" if count == 1 else "assets"
        return redirect(url_for(
            "locations",
            error=f"Cannot delete {location.name}: {count} {noun} are still assigned here. Move them first."
        ))

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

    sort_by = request.args.get("sort", "priority")

    items = db.session.execute(
        db.select(GoBagItem).join(GoBagItem.asset)
    ).scalars().all()

    if sort_by == "location":
        items.sort(
            key=lambda item: (
                item.asset.location.name.lower(),
                item.asset.name.lower()
            )
        )
    elif sort_by == "name":
        items.sort(key=lambda item: item.asset.name.lower())
    else:
        priority_order = {"High": 0, "Medium": 1, "Low": 2}
        items.sort(
            key=lambda item: (
                priority_order.get(item.priority, 3),
                item.asset.name.lower()
            )
        )
        sort_by = "priority"

    return render_template(
        "go_bag.html",
        items=items,
        sort_by=sort_by,
        user=user
    )


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

@app.route("/go-bag/<int:item_id>/update", methods=["POST"])
def update_go_bag_item(item_id):
    user = get_current_user()

    if user is None:
        return redirect(url_for("login"))

    item = db.session.get(GoBagItem, item_id)

    if item is None:
        abort(404)

    priority = request.form.get("priority", "").strip()
    notes = request.form.get("notes", "").strip()
    return_sort = request.form.get("return_sort", "priority")

    if priority not in {"High", "Medium", "Low"}:
        abort(400)

    item.priority = priority
    item.notes = notes or None

    db.session.commit()

    return redirect(url_for("go_bag", sort=return_sort))

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


@app.route("/insurance")
def insurance_records():
    user = get_current_user()

    if user is None:
        return redirect(url_for("login"))

    error = session.pop("insurance_error", None)

    asset_list = db.session.execute(
        db.select(Asset).order_by(Asset.name)
    ).scalars().all()

    insured_assets = [
        asset for asset in asset_list
        if asset.insurance_record is not None
    ]

    uninsured_assets = [
        asset for asset in asset_list
        if asset.insurance_record is None
    ]

    return render_template(
        "insurance.html",
        insured_assets=insured_assets,
        uninsured_assets=uninsured_assets,
        user=user,
        error=error
    )


@app.route("/assets/<int:asset_id>/insurance", methods=["POST"])
def save_insurance_record(asset_id):
    user = get_current_user()

    if user is None:
        return redirect(url_for("login"))

    asset = db.session.get(Asset, asset_id)
    if asset is None:
        abort(404)

    provider = request.form.get("provider", "").strip()
    policy_number = request.form.get("policy_number", "").strip()
    insured_value_text = request.form.get("insured_value", "").strip()
    evidence_reference = request.form.get("evidence_reference", "").strip()
    claim_ready = request.form.get("claim_ready") == "on"
    if not any([provider, policy_number, insured_value_text, evidence_reference]):
        session["insurance_error"] = "Enter at least one insurance detail before saving."
        return redirect(url_for("insurance_records"))

    insured_value = None
    if insured_value_text:
        try:
            insured_value = float(insured_value_text)
        except ValueError:
            abort(400)

        if insured_value < 0:
            abort(400)

    insurance_record = asset.insurance_record

    if insurance_record is None:
        insurance_record = InsuranceRecord(asset_id=asset.id)
        db.session.add(insurance_record)

    insurance_record.provider = provider or None
    insurance_record.policy_number = policy_number or None
    insurance_record.insured_value = insured_value
    insurance_record.evidence_reference = evidence_reference or None
    insurance_record.claim_ready = claim_ready

    db.session.commit()

    return redirect(url_for("insurance_records"))

@app.route("/assets/<int:asset_id>/insurance/delete", methods=["POST"])
def delete_insurance_record(asset_id):
    user = get_current_user()

    if user is None:
        return redirect(url_for("login"))

    asset = db.session.get(Asset, asset_id)

    if asset is None:
        abort(404)

    insurance_record = asset.insurance_record

    if insurance_record is None:
        abort(404)

    db.session.delete(insurance_record)
    db.session.commit()

    return redirect(url_for("insurance_records"))

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

@app.route("/reports/inventory.csv")
def export_inventory_csv():
    user = get_current_user()

    if user is None:
        return redirect(url_for("login"))

    if user.role != ROLE_ADMIN:
        abort(403)

    assets = db.session.execute(
        db.select(Asset).order_by(Asset.name)
    ).scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Asset ID",
        "Name",
        "Description",
        "Category",
        "Location",
        "Status",
        "Go-Bag",
        "Go-Bag Priority",
        "Claim Ready",
        "Insurance Provider",
        "Policy Reference",
        "Insured Value",
    ])

    for asset in assets:
        go_bag_item = asset.go_bag_item
        insurance_record = asset.insurance_record

        writer.writerow([
            asset.id,
            asset.name,
            asset.description or "",
            asset.category.name if asset.category else "",
            asset.location.name if asset.location else "",
            asset.status,
            "Yes" if go_bag_item else "No",
            go_bag_item.priority if go_bag_item else "",
            "Yes" if insurance_record and insurance_record.claim_ready else "No",
            insurance_record.provider if insurance_record else "",
            insurance_record.policy_number if insurance_record else "",
            insurance_record.insured_value
            if insurance_record and insurance_record.insured_value is not None
            else "",
        ])

    csv_content = output.getvalue()
    output.close()

    return Response(
        csv_content,
        mimetype="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=home_inventory_report.csv"
        },
    )