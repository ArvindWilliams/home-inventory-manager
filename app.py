from flask import Flask, render_template, request, session, redirect, url_for, abort
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

ROLE_ADMIN = "Administrator"
ROLE_USER = "User"

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

with app.app_context():
    db.create_all()

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
    status = db.Column(db.String(20), nullable=False, default="Active")

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

    return render_template(
        "assets.html",
        assets=asset_list,
        categories=categories,
        locations=locations,
        user=user
    )


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
            status="Active",
            category_id=int(category_id),
            location_id=int(location_id)
        )

        db.session.add(asset)
        db.session.commit()


        

    return redirect(url_for("assets"))

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