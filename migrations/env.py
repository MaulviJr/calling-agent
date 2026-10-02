from alembic import context
from dotenv import load_dotenv
from backend.app.database import Base, database

load_dotenv()
engine, _ = database()
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
engine.dispose()
