# Todo App

A Django REST Framework-powered Todo API that provides CRUD operations for managing tasks efficiently with support for listing, creating, updating, and deleting todos.

## Run Instructions

### Setup & Run
```bash
uv sync
python manage.py migrate
python manage.py runserver
```

### Testing
```bash
python manage.py test
```

### Environment Variables
| Variable | Description | Default |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | Secret key for cryptographic signing | `dev-insecure-key-change-me` |
| `DJANGO_DEBUG` | Enable/disable debug mode (`1` for True, `0` for False) | `1` |
| `DATABASE_PATH` | File path for the SQLite database | `BASE_DIR / 'db.sqlite3'` |

### API Endpoints

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/api/todos/` | List all todos |
| `POST` | `/api/todos/` | Create a new todo |
| `GET` | `/api/todos/{id}/` | Retrieve a specific todo |
| `PUT` | `/api/todos/{id}/` | Update a specific todo |
| `PATCH` | `/api/todos/{id}/` | Partially update a specific todo |
| `DELETE` | `/api/todos/{id}/` | Delete a specific todo |

### Example cURL Commands

**Create a todo:**
```bash
curl -X POST http://localhost:8000/api/todos/ \
  -H "Content-Type: application/json" \
  -d '{"title": "Buy groceries", "completed": false}'
```

**List all todos:**
```bash
curl http://localhost:8000/api/todos/
```
