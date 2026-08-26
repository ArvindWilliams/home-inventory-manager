# Home Inventory Manager

Home Inventory Manager (HIM) is a Flask-based web application developed for IFN636 Software Life Cycle Management.

The system supports household asset management across the asset lifecycle, including:

- Asset creation, editing and status management
- Category and location management
- Asset lending and return
- Emergency Go-Bag preparation
- Insurance evidence and claim readiness
- Search and filtering
- Inventory reporting and CSV export
- Role-based access for Administrator and User accounts

## Technology Stack

- Python
- Flask
- Flask-SQLAlchemy
- SQLite
- HTML / Jinja templates
- CSS
- Git and GitHub
- AWS EC2
- Gunicorn
- systemd
- Nginx

## Local Setup

1. Clone the repository.
2. Create and activate a Python virtual environment.
3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Set a Flask secret key in the environment, or use the development fallback configured in `app.py`.

```bash
export SECRET_KEY="your-local-development-secret"
```

5. Start the application:

```bash
flask --app app run
```

6. Open the local address shown by Flask in a browser.

The application uses SQLite for persistent storage. Database tables are created automatically with `db.create_all()` when the application starts.


## Roles

### Administrator

The Administrator can:

- Manage categories and locations
- Manage household assets
- Change permitted asset lifecycle states
- Lend and return assets
- Manage Emergency Go-Bag records
- Manage insurance evidence records
- Search and filter inventory
- Export inventory data to CSV

### User

The User can access permitted inventory workflows and view household inventory while Administrator-only category and location management functions remain restricted.

## Production Deployment

The application is deployed to an AWS EC2 Ubuntu instance.

Production architecture:

Browser → Nginx → Gunicorn → Flask → SQLite

- Nginx listens on port 80 and acts as the reverse proxy.
- Gunicorn runs the Flask application on the internal EC2 interface.
- systemd manages the Gunicorn service and restarts it automatically if required.
- The Flask production secret is stored in a protected EC2 environment file rather than committed to Git.
- SQLite provides persistent application storage on the EC2 instance.

The deployment was verified by confirming:

- Administrator login
- User login
- Role-based access restrictions
- Database write and read operations
- Data persistence after Gunicorn restart
- Nginx and Gunicorn active and enabled through systemd

## Known Limitations

- The application uses SQLite and is intended for a single-household deployment.
- User accounts are created administratively rather than through a self-service registration workflow.
- The production deployment currently uses HTTP rather than HTTPS.
- The EC2 public IP may change if the instance is stopped and restarted unless an Elastic IP is assigned.
- CI/CD automation is not currently configured; production updates are pulled from GitHub and the application service is restarted manually.

## Release

The production release is represented by the `v1.0.0` Git tag.

The release includes:

- Core asset management
- Asset lifecycle and status handling
- Lending and return workflow
- Emergency Go-Bag workflow
- Insurance evidence and claim readiness
- Search and filtering
- CSV reporting
- Administrator and User role-based access
- AWS EC2 production deployment
