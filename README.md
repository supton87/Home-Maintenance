# HomeCare Checklist

A web application for home-maintenance checklists.

- **Customers** log in and see only their own house(s), checklist, photos, and messages.
- **Technicians / Admins** manage customers, houses, checklist items, upload photos, and post messages.

## Features

- Separate checklist **per customer / per house**
- User roles: `admin` (tech) and `customer`
- Checklist items with category, priority, status, due date, and notes
- Photo uploads (attached to a checklist item **or** house gallery)
- Message board per house
- Clean Bootstrap 5 UI
- SQLite database (easy to start; can switch to PostgreSQL later)

## Quick Start

```bash
# 1. Create a virtual environment (recommended)
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the app
python app.py
```

Open http://127.0.0.1:5000 in your browser.

The database is created automatically the first time you run the app (SQLite).  
By default the code uses `/tmp/home_maintenance.db` so it works in restricted environments.  
On your own computer you can change the path in `app.py` to a local file such as:

```python
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///home_maintenance.db"
```

### Demo accounts (created automatically)

| Role     | Email               | Password     |
|----------|---------------------|--------------|
| Tech     | admin@example.com   | admin123     |
| Customer | sarah@example.com   | customer123  |
| Customer | mike@example.com    | customer123  |

## Project Structure

```
home_maintenance/
├── app.py                 # Main Flask application
├── models.py              # Database models
├── requirements.txt
├── static/uploads/        # Uploaded photos
├── templates/
│   ├── base.html
│   ├── dashboard.html     # Customer view
│   ├── house_detail.html  # Checklist + messages + gallery
│   ├── auth/login.html
│   └── admin/             # Tech tools
└── README.md
```

## Typical Tech Workflow

1. Log in as admin
2. Create a customer (Customers page)
3. Create a house and assign it to that customer (Houses page)
4. Add checklist items for the house
5. Upload photos and post messages on the house page
6. Customer logs in and sees only their houses

## Production Notes

- Change `SECRET_KEY` (use an environment variable)
- Switch from SQLite to PostgreSQL when you have multiple users
- Put uploaded files on cloud storage (S3, etc.) instead of local disk
- Add HTTPS and proper password-reset flow
- Consider email notifications for due dates

## License

MIT – free to use and modify for your business.
